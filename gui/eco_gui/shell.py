"""窓の開け方。Electron が入っていればアプリの窓で、なければ GUIFrameWork の既定（Edge・Chrome の窓）で開く。

Electron 本体は、今の GUI が入れたもの（gui/electron/node_modules）を使う。場所は環境変数 ECOBUILD_GUI_ELECTRON でも決められる。

Electron には、窓の URL・題・大きさのほかに、モジュールの窓をタスクバーで「モジュールごとのアプリ」にするための材料を渡す
（electron/main.js）：型ごとのアイコン（--type-icons）と、ピン留めした窓から開き直すときの起動のしかた（--launch：
この GUI の pythonw と ECOBuildGUINext.pyw。モジュールの窓なら、後ろに --module <場所> を足して開き直す）。
"""

import functools
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from guiframework import open_in_browser

HERE = Path(__file__).resolve().parent
APP = HERE / "electron"  # main.js・package.json
GUI = HERE.parent         # gui/（ECOBuildGUINext.pyw・module.ico）


def electron() -> str | None:
    """Electron の実行ファイル。なければ None。"""
    chosen = os.environ.get("ECOBUILD_GUI_ELECTRON")
    if chosen:
        return chosen if Path(chosen).is_file() else None
    dist = HERE.parent / "electron" / "node_modules" / "electron" / "dist"
    names = {"win32": "electron.exe", "darwin": "Electron.app/Contents/MacOS/Electron"}
    found = dist / names.get(sys.platform, "electron")
    return str(found) if found.is_file() else None


@functools.lru_cache(maxsize=1)
def type_icons() -> dict[str, str]:
    """型 → アイコン（.ico）の場所（ecobuild module types の icon_ico）。中継地点が動くあいだ、1回だけ聞く。"""
    ecobuild = os.environ.get("ECOBUILD_GUI_ECOBUILD") or shutil.which("ecobuild") or "ecobuild"
    flags = 0x08000000 if sys.platform == "win32" else 0
    try:
        done = subprocess.run([ecobuild, "module", "types", "--json"], capture_output=True, encoding="utf-8", errors="replace",
                              stdin=subprocess.DEVNULL, timeout=60, creationflags=flags)
        result = json.loads(done.stdout.strip().splitlines()[-1]).get("result") or []
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return {}
    return {str(t["name"]): str(t["icon_ico"]) for t in result if isinstance(t, dict) and t.get("name") and t.get("icon_ico")}


def launch() -> list[str]:
    """この GUI を開き直す起動のしかた：窓のない Python（今の Python の隣の pythonw）と ECOBuildGUINext.pyw。"""
    python = Path(sys.executable)
    windowless = python.with_name("pythonw.exe")
    return [str(windowless if sys.platform == "win32" and windowless.is_file() else python), str(GUI / "ECOBuildGUINext.pyw")]


def electron_command(exe: str, url: str, title: str, size: list[int]) -> list[str]:
    return [exe, str(APP), f"--url={url}", f"--title={title}", f"--size={size[0]}x{size[1]}",
            f"--launch={json.dumps(launch(), ensure_ascii=False)}", f"--type-icons={json.dumps(type_icons(), ensure_ascii=False)}",
            f"--module-icon={GUI / 'module.ico'}"]


def open_window(url: str, title: str, size: list[int]) -> None:
    if os.environ.get("GUIFRAMEWORK_NO_WINDOW"):  # 試験用：開かない（GUIFrameWork の既定と同じ）
        return
    exe = electron()
    if exe is None:
        open_in_browser(url, title, size)
        return
    # 型のアイコンを初めて聞くときは ecobuild を呼ぶ（1秒ほど）：中継地点を待たせないよう、別の流れで起こす
    threading.Thread(target=_start, args=(exe, url, title, size), daemon=True).start()


def _start(exe: str, url: str, title: str, size: list[int]) -> None:
    env = {k: v for k, v in os.environ.items() if k != "ELECTRON_RUN_AS_NODE"}  # 付いていると、窓のアプリとして動かない
    flags = 0x08000000 if sys.platform == "win32" else 0  # コマンドプロンプトの窓を出さない
    try:
        subprocess.Popen(electron_command(exe, url, title, size),
                         env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    except OSError:
        open_in_browser(url, title, size)
