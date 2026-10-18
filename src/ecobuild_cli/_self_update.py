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

from ecobuild.errors import EcoBuildError, ErrorCode

_COMMIT = re.compile(r"[0-9a-f]{40}")
GUI_DIRECTORY = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "ECOBuild GUI"   # install.ps1 の置き場所


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
    gui: bool = False        # GUI も入れ直す


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


def check(ref: str | None = None) -> SelfUpdate:
    """入れ元の版（ref で別の版に変えられる）の最新と、入っているものを比べる。"""
    current = installed()
    if current.editable:
        raise EcoBuildError(ErrorCode.NOT_UPDATABLE,
                            f"この ecobuild は開発用に手元のソース（{current.url}）から入っています。",
                            hint="ソースを更新（git pull 等）すれば、そのまま反映されます。")
    target = ref or current.ref or "HEAD"
    latest = target if _COMMIT.fullmatch(target) else _remote_commit(current.url, target)
    return SelfUpdate(current.url, target, current.commit, latest, latest == current.commit)


def update(ref: str | None = None) -> SelfUpdate:
    """新しければインストーラーで入れ直す。Windows は別の窓で始めて戻る（started）。"""
    result = check(ref)
    if result.up_to_date:
        return result
    gui = (GUI_DIRECTORY / "app.py").is_file()
    script = _installer(result.url, result.latest, "install.ps1" if os.name == "nt" else "install.sh")
    if os.name == "nt":
        command = (f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue; "
                   f"& {_quote(script)} -Ref {_quote(result.ref)} -NoInit{'' if gui else ' -NoGui'}; "
                   "Write-Host ''; Read-Host '閉じるには Enter を押してください'")
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                         creationflags=subprocess.CREATE_NEW_CONSOLE, cwd=str(script.parent))
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
