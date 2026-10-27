"""ECOBuild 自体（CLI と GUI）の更新（ecobuild installer update）。

入れたときの記録（pip の direct_url.json）から入れ元の git のリポジトリと版（ブランチ等）を知り、GitHub のその版の
最新と比べる。更新はインストーラー（installer/install.ps1・install.sh）に任せる：CLI（pipx）と GUI を同じ版で
入れ直す手順を2か所に持たないため。Windows では動いている ecobuild.exe を置き換えられないので、別の窓で、
この ecobuild が終わるのを待ってから行う。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from ecobuild.errors import EcoBuildError
from ecobuild.errors import ErrorCode as _ErrorCode

_COMMIT = re.compile(r"[0-9a-f]{40}")
GUI_DIRECTORY = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "ECOBuild GUI"   # install.ps1 の置き場所


class ErrorCode(_ErrorCode):
    NOT_UPDATABLE = "not_updatable"     # installer update：入れ方（手元のソース・同梱のインストーラー等）から更新できない


@dataclass(frozen=True)
class Installed:
    """今の ecobuild の入れ元。"""
    url: str                 # git のリポジトリ（手元のソースならそのURL）
    ref: str | None          # 入れたときに指定した版（ブランチ・タグ・コミット）
    commit: str | None       # 入っているコミット
    editable: bool = False   # 手元のソースから（開発用）


@dataclass(frozen=True)
class SelfUpdate:
    url: str
    ref: str
    current: str | None      # 入っているコミット
    latest: str              # GitHub のその版の最新のコミット
    up_to_date: bool
    started: bool = False    # 更新を始めた（Windows：別の窓で。終わるまで待たない）
    gui: bool = False        # GUI も入れ直す（インストーラーが入れた GUI があるとき）
    process: int | None = None   # 更新している窓のプロセス（Windows。これが終われば更新も終わっている）


def installed() -> Installed:
    try:
        text = metadata.distribution("ecobuild").read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        text = None
    data = json.loads(text) if text else {}
    if "vcs_info" in data:
        vcs = data["vcs_info"]
        return Installed(data["url"], vcs.get("requested_revision"), vcs.get("commit_id"))
    if data.get("dir_info", {}).get("editable"):
        return Installed(data["url"], None, None, editable=True)
    raise EcoBuildError(ErrorCode.NOT_UPDATABLE, "この ecobuild は、入れ元が分からないため更新できません。",
                        hint="インストーラー（installer/install.ps1 等）をもう一度実行して入れ直してください。")


@dataclass(frozen=True)
class Version:
    """入れられる版の候補（ブランチ・タグのコミット）。"""
    sha: str
    date: str                # コミットの日時（ISO 8601）
    subject: str
    current: bool = False    # 今入っている版
    latest: bool = False     # そのブランチ・タグの最新


@dataclass(frozen=True)
class Versions:
    url: str
    installed_ref: str | None   # 入れたときに指定した版
    current: str | None         # 入っているコミット
    ref: str                    # 候補（commits）を出したブランチ・タグ
    default_branch: str | None  # 入れ元のリポジトリの既定のブランチ（分からなければ None）
    branches: tuple[str, ...]   # ref が先頭、次に既定のブランチ、ほかは名前順
    tags: tuple[str, ...]       # 新しい版が先
    commits: tuple[Version, ...]   # ref の最近のコミット（新しい順）


def _updatable() -> Installed:
    current = installed()
    if current.editable:
        raise EcoBuildError(ErrorCode.NOT_UPDATABLE,
                            f"この ecobuild は開発用に手元のソース（{current.url}）から入っています。",
                            hint="ソースを更新（git pull 等）すれば、そのまま反映されます。")
    return current


def versions(ref: str | None = None, count: int = 30) -> Versions:
    """入れられる版の候補：入れ元のリポジトリのブランチ・タグと、ref（省略時は入れたときのブランチ、コミットを入れて
    いれば既定のブランチ）の最近のコミット。update --ref に渡して入れ直す（前の版へ戻すのにも）。"""
    current = _updatable()
    branches, tags = [], []
    for line in _git("ls-remote", "--heads", "--tags", current.url).splitlines():
        name = line.split("\t")[-1].strip()
        if name.startswith("refs/heads/"):
            branches.append(name.removeprefix("refs/heads/"))
        elif name.startswith("refs/tags/") and not name.endswith("^{}"):
            tags.append(name.removeprefix("refs/tags/"))
    default = _default_branch(current.url)
    installed_branch = current.ref if current.ref in branches else None
    target = ref or installed_branch or default or (branches[0] if branches else None)
    if not target or (target not in branches and target not in tags and not _COMMIT.fullmatch(target)):
        raise EcoBuildError(ErrorCode.REVISION_NOT_FOUND, f"{current.url} に版 {target or '（ブランチがありません）'} がありません。",
                            hint="--ref でブランチ・タグを指定してください。")
    first = [b for b in dict.fromkeys([target, installed_branch, default]) if b in branches]
    ordered = first + sorted(b for b in branches if b not in first)
    commits = _recent_commits(current.url, target, count)
    return Versions(current.url, current.ref, current.commit, target, default, tuple(ordered),
                    tuple(sorted(tags, key=_natural, reverse=True)),
                    tuple(Version(sha, date, subject, sha == current.commit, i == 0)
                          for i, (sha, date, subject) in enumerate(commits)))


def _default_branch(url: str) -> str | None:
    for line in _git("ls-remote", "--symref", url, "HEAD").splitlines():
        if line.startswith("ref: refs/heads/"):
            return line.removeprefix("ref: refs/heads/").split("\t")[0].strip()
    return None


def _recent_commits(url: str, ref: str, count: int) -> list[tuple[str, str, str]]:
    """ref の最近のコミット（sha・日時・件名）。中身（ファイル）は取らない（--filter=tree:0）。"""
    with tempfile.TemporaryDirectory(prefix="ecobuild-versions-", ignore_cleanup_errors=True) as directory:
        _git("init", "--quiet", directory)
        _git("-C", directory, "fetch", "--quiet", "--filter=tree:0", "--depth", str(max(count, 1)), url, ref)
        listed = _git("-C", directory, "log", "--format=%H%x1f%cI%x1f%s", "FETCH_HEAD")
    return [tuple(line.split("\x1f", 2)) for line in listed.splitlines() if line.count("\x1f") >= 2]


def _natural(name: str) -> list:
    """v1.10 が v1.9 より後になるように（数字は数として比べる）。"""
    return [(1, int(part), "") if part.isdigit() else (0, 0, part) for part in re.split(r"(\d+)", name)]


def check(ref: str | None = None) -> SelfUpdate:
    """入れ元の版（ref で別の版に変えられる）の最新と、入っているものを比べる。"""
    current = _updatable()
    target = ref or current.ref or "HEAD"
    latest = target if _COMMIT.fullmatch(target) else _remote_commit(current.url, target)
    return SelfUpdate(current.url, target, current.commit, latest, latest == current.commit,
                      gui=(GUI_DIRECTORY / "app.py").is_file())


def update(ref: str | None = None) -> SelfUpdate:
    """新しければインストーラーで入れ直す。Windows は別の窓で始めて戻る（started）。"""
    result = check(ref)
    if result.up_to_date:
        return result
    gui = result.gui
    script = _installer(result.url, result.latest, "install.ps1" if os.name == "nt" else "install.sh")
    if os.name == "nt":
        command = (f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue; "
                   f"& {_quote(script)} -Ref {_quote(result.ref)} -NoInit{'' if gui else ' -NoGui'}; "
                   # うまくいけば少し見せて閉じる（待っている人＝GUI の起動し直しがすぐ進む）。失敗なら読めるように待つ
                   "if ($LASTEXITCODE -ne 0) { Write-Host ''; Read-Host '閉じるには Enter を押してください' } "
                   "else { Start-Sleep -Seconds 3 }")
        process = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                                   creationflags=subprocess.CREATE_NEW_CONSOLE, cwd=str(script.parent))
        return SelfUpdate(result.url, result.ref, result.current, result.latest, False, started=True, gui=gui,
                          process=process.pid)
    else:
        completed = subprocess.run(["bash", str(script), "--ref", result.ref, "--no-init"])
        if completed.returncode != 0:
            raise EcoBuildError(ErrorCode.NOT_UPDATABLE, "インストーラーが失敗しました。",
                                hint=f"表示を確かめて、bash {script} --ref {result.ref} を実行し直してください。")
    return SelfUpdate(result.url, result.ref, result.current, result.latest, False, started=True, gui=gui)


def _remote_commit(url: str, ref: str) -> str:
    listed = _git("ls-remote", url, ref)
    commits = [line.split()[0] for line in listed.splitlines() if line.strip()]
    if not commits:
        raise EcoBuildError(ErrorCode.REVISION_NOT_FOUND, f"{url} に版 {ref} がありません。",
                            hint="--ref でブランチ・タグ・コミットを指定してください。")
    return commits[0]


def _installer(url: str, commit: str, name: str) -> Path:
    """その版のインストーラーを取り出す（入れるのと同じ版の手順で入れる）。"""
    directory = Path(tempfile.mkdtemp(prefix="ecobuild-update-"))
    _git("init", "--quiet", str(directory))
    _git("-C", str(directory), "fetch", "--quiet", "--depth", "1", url, commit)
    script = directory / name
    script.write_bytes(subprocess.run(["git", "-C", str(directory), "show", f"FETCH_HEAD:installer/{name}"],
                                      capture_output=True, check=True).stdout)
    return script


def _git(*args: str) -> str:
    if shutil.which("git") is None:
        raise EcoBuildError(ErrorCode.TOOL_MISSING, "git が見つかりません。", hint="git を入れてから実行してください。")
    completed = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise EcoBuildError(ErrorCode.GIT_ERROR, f"git {args[0]} に失敗しました。", details=completed.stderr.strip())
    return completed.stdout


def _quote(value: object) -> str:
    """PowerShell の文字列（'…'）。"""
    return "'" + str(value).replace("'", "''") + "'"
