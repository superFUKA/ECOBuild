"""依存先の版（deps add・deps update・deps libraries の --at、deps versions の --branch）が GitHub から取れるかを確かめる。

CppBuild は版をこう解く：ブランチ・タグは GitHub に問い合わせ（ls-remote）、長いハッシュはそのまま記録し（取るのは clone・
checkout のとき）、短いハッシュは手元の clone（deps/<名前>）の中だけで解く。そのため、
- 手元の clone を取り込み直していないと、GitHub に push 済みのコミットでも短いハッシュが解けない
- GitHub のブランチにないコミット（push していない・PR の中だけ）の長いハッシュも記録でき、後の clone で失敗する。
ここで先に、手元の clone を取り込み直して長いハッシュにし、GitHub のブランチにないなら、このPCのどこにあるかを添えて断る。
探す場所は、手元の clone と、このPCのモジュールの一覧（ecobuild workspace list）にある同じリポジトリの元の clone（作業空間の
コミットも、元の clone から見える）。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from ecowork.git import Git

from ecobuild import workspaces as _workspaces
from ecobuild.errors import EcoBuildError, operation

from .errors import ErrorCode

HEX = re.compile(r"[0-9a-f]{4,64}")   # コミットのハッシュ（短い・長い）に見える版
PUSH_RULE = ("コミットは、GitHub のブランチに push したものだけ使えます（push していないもの・PR の中だけにあるもの"
             "〔取り込んでブランチを消した等〕は使えません）。")


def commit_for(url: str, revision: str | None, clone: Path | str | None = None, *, command: str = "") -> str | None:
    """revision がコミットのハッシュなら、GitHub のブランチにあることを確かめて長いハッシュを返す。

    ブランチ・タグの名前や、どこにも見つからないときは None（CppBuild に任せる）。手元にあって GitHub のブランチにないなら、
    どこにあるかを添えた EcoBuildError（DEPENDENCY_REVISION_NOT_FOUND）。clone：依存先の手元の clone（deps/<名前>）。"""
    if not revision or not HEX.fullmatch(revision.lower()):
        return None
    revision = revision.lower()
    own = Path(clone) if clone is not None and (Path(clone) / ".git").exists() else None
    places = ([own] if own else []) + [path for path in local_copies(url) if not own or not _workspaces.same(path, own)]
    for place in places:
        git = Git(place, command=command)
        try:
            git.fetch(reuse=place is not own)   # GitHub のブランチを今のものに（依存先の clone は必ず取り込み直す）
        except Exception:   # 取り込めない（オフライン等）：手元の写しで確かめる
            pass
        sha = git.rev_parse(revision)
        if sha is None or not sha.startswith(revision):   # ない・同じ名前のブランチ等
            continue
        if git.run("branch", "--remotes", "--contains", sha, check=False).stdout.strip():
            return sha
        raise _not_pushed(url, revision, sha, place, git, is_clone=place is own, command=command)
    return None


def unresolved(name: str | None, url: str, revision: str, error: EcoBuildError, *, command: str = "") -> EcoBuildError:
    """CppBuild が版を取れなかったときの誤り（手元のどこにも見つからなかった版）。name：依存先の名前（まだ依存先でなければ None）。"""
    short = HEX.fullmatch(revision.lower()) is not None and len(revision) < 40
    choices = f"候補は {operation(command, 'deps versions')} {name}" if name else "候補は GitHub のリポジトリで確かめられます"
    hint = f"ブランチ・タグ・コミットが GitHub の {_shown(url)} にあるか確かめてください（{choices}）。" + PUSH_RULE
    if short:
        hint += "短いハッシュが解けないときは、長いハッシュかブランチ名で指定してください。"
    return EcoBuildError(error.code, f"{'依存先 ' + name if name else _shown(url)} の版 {revision} を、GitHub の {_shown(url)} から"
                                     f"取得できません。", hint=hint, details=error.details)


def branch_hint(url: str, branch: str, *, command: str = "") -> str | None:
    """GitHub にないブランチが、このPCの同じリポジトリにあれば、どこにあって push されていないかの文（なければ None）。"""
    for place in local_copies(url):
        git = Git(place)
        if git.rev_parse(f"refs/heads/{branch}") is None:
            continue
        where = _checked_out(git).get(branch, place)
        return (f"ブランチ {branch} は、このPCの {where} にあり、GitHub へ push されていません。そこで push "
                f"（タスクブランチなら {operation(command, 'task push')}）してから、もう一度選んでください。")
    return None


def local_copies(url: str) -> list[Path]:
    """このPCのモジュールの一覧にある、url と同じリポジトリの元の clone。"""
    wanted = _repository_key(url)
    found = []
    for item in _workspaces.recorded():
        path = Path(item.path)
        if not (path / ".git").exists():
            continue
        origin = Git(path).get_config("remote.origin.url") or item.url
        if origin and _repository_key(origin) == wanted:
            found.append(path)
    return found


def _not_pushed(url: str, revision: str, sha: str, place: Path, git: Git, *, is_clone: bool,
                command: str) -> EcoBuildError:
    branches = [line.strip() for line in git.run("for-each-ref", "--contains", sha, "--format=%(refname:short)",
                                                  "refs/heads", check=False).stdout.splitlines() if line.strip()]
    checked = _checked_out(git)
    holder = next((b for b in branches if b in checked), branches[0] if branches else None)
    where = checked.get(holder, place) if holder else place
    if holder is None:
        found = f"このPCの {where} にありますが、どのブランチにもありません"
    else:
        found = f"このPCの {where}（ブランチ {holder}）にあり、まだ push されていません"
    if is_clone:
        todo = "依存先の手元の clone で作ったコミットです。その clone から GitHub のブランチへ push してから、もう一度実行してください。"
    else:
        todo = (f"そこで push（タスクブランチなら {operation(command, 'task push')}）してから、もう一度実行してください。"
                if holder else "GitHub のブランチにあるコミットを選んでください。")
    return EcoBuildError(ErrorCode.DEPENDENCY_REVISION_NOT_FOUND,
                         f"コミット {revision} は、GitHub の {_shown(url)} のブランチにありません（{found}）。",
                         hint=todo + PUSH_RULE, details=f"コミット：{sha}")


def _checked_out(git: Git) -> dict[str, Path]:
    """ブランチ → それを出している場所（元の clone と、その作業空間）。"""
    found = {}
    lines = git.run("for-each-ref", "--format=%(refname:short) %(worktreepath)", "refs/heads", check=False).stdout
    for line in lines.splitlines():
        name, _, path = line.partition(" ")
        if path.strip():
            found[name] = Path(path.strip())
    return found


def _repository_key(url: str) -> str:
    """同じリポジトリかを比べる値：手元の場所（file: の URL も）は場所、ほかは 所有者/名前（ecobuild の比べ方）。"""
    text = url.strip()
    if text.lower().startswith("file:"):
        return _workspaces.key(url2pathname(urlparse(text).path))
    if os.path.isabs(text):
        return _workspaces.key(text)
    return _workspaces.identity(text) or text


def _shown(url: str) -> str:
    return _workspaces.github_name(url) or url
