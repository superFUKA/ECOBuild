"""依存先の作業版（deps work）：依存先の手元の clone（deps/<名前>）を、作りかけのブランチ（依存先のタスクブランチ等）の
最新にする。記録の版（CppBuild の git_sources）は変えない。

取ってくる先は、このPCに依存先のモジュールの元の clone があり、そのブランチを取り出している作業空間（.ecobuild/w/<番号>）
等があればそこ（push していないコミットも使える）。なければ GitHub のブランチ（push 済みのものだけ）。コンテナの中
（エージェント）では元の clone が見えないので、GitHub から取る。remote は足さず `git fetch <場所> <ブランチ>` で取る。

作業版の clone はブランチを作らず、取ってきたコミットで切り離す（deps/ の中で ecobuild を動かしても依存先のタスクブランチに
見えず、task commit・push で作りかけが依存先の GitHub に出ない）。どこから何を取ったかは、依存先の clone の git の設定
（ecobuild-work.*。コミットされない）にだけ覚える。依存先の側を変えるのは、
依存先のモジュールの自分のタスク（その作業空間）でだけ。deps/ の中でコミット・push する道は作らない。
"""

from __future__ import annotations

from pathlib import Path

from ecowork import model as wm
from ecowork.git import Git

from ecobuild.errors import EcoBuildError, operation
from ecobuild.results import DependencyWorkSource

from . import _revisions
from .errors import ErrorCode

SECTION = "ecobuild-work"   # 依存先の clone の git の設定の節（branch・task・origin・place・commit）
LOCAL, GITHUB = "local", "github"


def read(clone: Git) -> DependencyWorkSource | None:
    """手元の clone が作業版なら、そのブランチと取ってきた先。deps work で切り替えた（取ってきたコミットで切り離し、
    どのブランチかは設定にだけある）か、タスクブランチを出している（依存先の中で task start した〔I-019〕。取ってきた先は
    分からない）。作業版でなければ None。"""
    branch = clone.current_branch()
    recorded = clone.get_config(f"{SECTION}.branch")
    if recorded and branch is None:
        task = clone.get_config(f"{SECTION}.task")
        return DependencyWorkSource(recorded, int(task) if task and task.isdigit() else wm.task_number(recorded),
                                    clone.get_config(f"{SECTION}.origin"), clone.get_config(f"{SECTION}.place"),
                                    clone.get_config(f"{SECTION}.commit"))
    if branch is not None and wm.is_task_branch(branch):
        return DependencyWorkSource(branch, wm.task_number(branch))
    return None


def remember(clone: Git, work: DependencyWorkSource) -> None:
    forget(clone)
    for key, value in (("branch", work.branch), ("task", None if work.task is None else str(work.task)),
                       ("origin", work.origin), ("place", work.place), ("commit", work.commit)):
        if value is not None:
            clone.run("config", "--local", f"{SECTION}.{key}", value)


def forget(clone: Git) -> None:
    clone.run("config", "--local", "--remove-section", SECTION, check=False)


def locate(name: str, url: str, *, task: int | None, branch: str | None, command: str = "") -> tuple[str, str, str]:
    """取ってくるブランチと先：(ブランチ, origin〔local／github〕, 場所〔取り出している作業空間か URL〕)。

    このPCの同じリポジトリ（元の clone）で、そのブランチを取り出している所（元の clone・作業空間）があれば、そこ。
    なければ GitHub。どちらにもなければ断る（このPCにあって取り出していないだけなら、そう添える）。"""
    unchecked: list[tuple[str, Path]] = []   # このPCにあるが、どこにも取り出していないブランチ
    for path in _revisions.local_copies(url):
        git = Git(path)
        names = _branches(git.output("for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines(),
                          task=task, branch=branch)
        if len(names) > 1:
            raise _ambiguous(name, task, names, command)
        if not names:
            continue
        place = {b: p for b, p in _revisions._checked_out(git).items() if p.is_dir()}.get(names[0])
        if place is not None:
            return names[0], LOCAL, str(place)
        unchecked.append((names[0], path))
    listed = Git(Path.cwd()).run("ls-remote", "--heads", "--", url, check=False)
    if not listed.ok:
        raise EcoBuildError(ErrorCode.GIT_ERROR, f"依存先 {name} の GitHub（{_revisions._shown(url)}）のブランチを読めません。",
                            hint="ネットワーク・アカウントを確かめてください。"
                                 + ("依存先のモジュールがこのPCにあれば、その作業空間から取れます。" if not unchecked else ""),
                            details=listed.output)
    remote = [line.partition("\t")[2].strip().removeprefix("refs/heads/") for line in listed.stdout.splitlines() if "\t" in line]
    names = _branches(remote, task=task, branch=branch)
    if len(names) > 1:
        raise _ambiguous(name, task, names, command)
    if names:
        return names[0], GITHUB, url
    wanted = f"タスク #{task} のブランチ（task/{task}-…）" if task is not None else f"ブランチ {branch}"
    if unchecked:
        found, path = unchecked[0]
        hint = (f"このPCの {path} にブランチ {found} がありますが、作業空間で取り出していません。依存先のモジュールで "
                f"{operation(command, 'task start')} {task if task is not None else ''}".rstrip()
                + f" をするか、{operation(command, 'task push')} で GitHub へ push してから、もう一度実行してください。")
    elif task is not None:
        hint = (f"依存先のモジュール（{_revisions._shown(url)}）で {operation(command, 'task start')} {task} をして作業し、"
                f"このPCにないなら {operation(command, 'task push')} で GitHub へ push してから、もう一度実行してください。")
    else:
        hint = f"ブランチの名前を確かめてください（GitHub のブランチ：{'、'.join(remote[:10]) or 'なし'}）。"
    raise EcoBuildError(ErrorCode.BRANCH_NOT_FOUND,
                        f"依存先 {name} の{wanted}が、このPCの作業空間にも GitHub にもありません。", hint=hint)


def _branches(names, *, task: int | None, branch: str | None) -> list[str]:
    if task is not None:
        return sorted(n for n in names if wm.task_number(n) == task)
    return [n for n in names if n == branch]


def _ambiguous(name: str, task: int | None, names: list[str], command: str) -> EcoBuildError:
    return EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                         f"依存先 {name} のタスク #{task} のブランチが {len(names)} つあります（{'、'.join(names)}）。",
                         hint=f"{operation(command, 'deps work')} {name} --branch <ブランチ> で選んでください。")


def github_ahead(clone: Git, url: str, branch: str, commit: str) -> bool:
    """GitHub の branch の先が、取ってきた commit に含まれない（GitHub の方が新しい・別の履歴）。読めなければ False。"""
    listed = clone.run("ls-remote", "--heads", "--", url, f"refs/heads/{branch}", check=False)
    tip = listed.stdout.split()[0] if listed.ok and listed.stdout.strip() else None
    if tip is None or tip == commit:
        return False
    return clone.rev_parse(tip) is None or not clone.is_ancestor(tip, commit)


def fetch(clone: Git, place: str, branch: str) -> str:
    """場所 place（作業空間・元の clone のパスか URL）のブランチ branch を取り込み、そのコミットを返す（remote は足さない）。"""
    done = clone.run("fetch", "--quiet", "--no-tags", "--", place, f"refs/heads/{branch}", check=False)
    if not done.ok:
        raise EcoBuildError(ErrorCode.GIT_ERROR, f"{place} からブランチ {branch} を取り込めません。", details=done.output)
    return clone.output("rev-parse", "FETCH_HEAD^{commit}").strip()
