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

HEX = re.compile(r"[0-9a-f]{7,64}")   # コミットのハッシュ（7文字以上の短いもの・長いもの）に見える版
NAMEISH = re.compile(r"[0-9a-f]{4,64}")   # CppBuild がまず手元の clone のコミットとして解く版（16進に見える名前もここに入る）
FULL = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
PUSH_RULE = ("コミットは、GitHub のブランチに push したものだけ使えます（push していないもの・PR の中だけにあるもの"
             "〔取り込んでブランチを消した等〕は使えません）。")


def commit_for(url: str, revision: str | None, clone: Path | str | None = None, *, command: str = "") -> str | None:
    """revision がコミットのハッシュなら、GitHub のブランチにあることを確かめて長いハッシュを返す。

    ブランチ・タグの名前（16進に見えても、GitHub にその名前があれば名前）や、確かめられないとき（GitHub に問い合わせられない・
    どこにも見つからず依存先の clone もない）は None（CppBuild に任せる）。断るのは DEPENDENCY_REVISION_NOT_FOUND で：
    手元にあって GitHub のブランチにない（どこにあるかを添える）・依存先の clone を取り込み直しても見つからない。
    短いハッシュが複数のコミットに当たるときは INVALID_ARGUMENT。clone：依存先の手元の clone（deps/<名前>）。"""
    if not revision or not NAMEISH.fullmatch(revision.lower()):
        return None
    # GitHub にその名前のブランチ・タグがあれば、その指すコミット（CppBuild は 16 進に見える名前を手元のコミットとして解いてしまう）
    named = _named(url, revision, own=clone)
    if named is not False:
        return named or None
    revision = revision.lower()
    if not HEX.fullmatch(revision):
        return None
    own = Path(clone) if clone is not None and (Path(clone) / ".git").exists() else None
    missing_on_github = False   # 依存先の clone を取り込み直して、なかった
    for place in _places(url, own):
        git = Git(place, command=command)
        fetched = False
        sha = _lookup(git, revision)
        if sha is None or not _on_github(git, sha):   # 手元の写しで足りなければ、取り込み直して確かめ直す
            fetched = _fetch(git, reuse=place is not own)
            if not fetched:   # GitHub に問い合わせられない：依存先の clone なら確かめるのをやめる・ほかの場所は飛ばす
                if place is own:
                    return None
                continue
            sha = _lookup(git, revision)
        if sha is None:
            missing_on_github = missing_on_github or (place is own and fetched)
            continue
        if _on_github(git, sha):
            return sha
        raise _not_pushed(url, revision, sha, place, git, is_clone=place is own, command=command)
    if missing_on_github:
        raise EcoBuildError(
            ErrorCode.DEPENDENCY_REVISION_NOT_FOUND,
            f"コミット {revision} は、GitHub の {_shown(url)} のブランチにありません（このPCのモジュールにも見つかりません）。",
            hint=f"ハッシュを確かめてください（候補は {operation(command, 'deps versions')} <依存先>）。" + PUSH_RULE)
    return None


def _places(url: str, own: Path | None):
    """探す場所：依存先の clone、次にこのPCの同じリポジトリの元の clone（要るときだけ読む）。"""
    if own is not None:
        yield own
    for path in local_copies(url):
        if own is None or not _workspaces.same(path, own):
            yield path


def _fetch(git: Git, *, reuse: bool) -> bool:
    """GitHub の今のブランチ・タグを取り込む。できなければ False（オフライン等。古い写しでは断らない）。"""
    try:
        git.fetch(reuse=reuse)
        if not reuse:
            git.run("fetch", "--quiet", "--tags", "--force", "origin")
        return True
    except Exception:
        return False


def _named(url: str, revision: str, *, own: Path | str | None) -> str | None | bool:
    """GitHub のブランチ・タグ revision の指すコミット（1234・cafe 等の16進に見える名前も）。その名前がなければ False、
    GitHub に問い合わせられなければ None（確かめずに CppBuild に任せる）。"""
    place = Path(own) if own is not None and Path(own).is_dir() else Path.cwd()
    try:
        done = Git(place).run("ls-remote", "--", url, f"refs/heads/{revision}", f"refs/tags/{revision}",
                              f"refs/tags/{revision}^{{}}", check=False)
    except Exception:
        return None
    if not done.ok:
        return None
    refs = {}
    for line in done.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        refs[ref.strip()] = sha.strip()
    for ref in (f"refs/tags/{revision}^{{}}", f"refs/tags/{revision}", f"refs/heads/{revision}"):
        if FULL.fullmatch(refs.get(ref, "")):
            return refs[ref]
    return False


def _lookup(git: Git, revision: str) -> str | None:
    """そのハッシュのコミット（なければ None）。短いハッシュが複数のコミットに当たれば、そう言って断る。"""
    sha = git.rev_parse(revision)
    if sha is not None and sha.startswith(revision):
        return sha
    if FULL.fullmatch(revision):
        return None
    listed = git.run("rev-parse", f"--disambiguate={revision}", check=False).stdout.split()
    commits = [item for item in listed
               if git.run("cat-file", "-t", item, check=False).stdout.strip() == "commit"]
    if len(commits) > 1:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                            f"短いハッシュ {revision} は、{len(commits)} 個のコミットに当たります。",
                            hint=f"もっと長いハッシュで指定してください（{'・'.join(c[:12] for c in commits[:5])}）。")
    return None


def _on_github(git: Git, sha: str) -> bool:
    """GitHub のブランチ（refs/remotes/origin）のどれかにあるか。"""
    return bool(git.run("for-each-ref", "--contains", sha, "--count=1", "--format=%(refname)", "refs/remotes/origin",
                        check=False).stdout.strip())


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


def local_copies(url: str):
    """このPCのモジュールの一覧にある、url と同じリポジトリの元の clone（見つけた順に。要る分だけ読む）。"""
    wanted = _repository_key(url)
    for item in _workspaces.recorded():
        path = Path(item.path)
        if not (path / ".git").exists():
            continue
        origin = Git(path).get_config("remote.origin.url") or item.url
        if origin and _repository_key(origin) == wanted:
            yield path


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
