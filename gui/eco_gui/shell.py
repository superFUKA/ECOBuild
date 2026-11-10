"""窓の開け方。Electron が入っていればアプリの窓で、なければ GUIFrameWork の既定（Edge・Chrome の窓）で開く。

Electron 本体は、今の GUI が入れたもの（gui/electron/node_modules）を使う。場所は環境変数 ECOBUILD_GUI_ELECTRON でも決められる。
"""

import os
import subprocess
import sys
from pathlib import Path

from guiframework import open_in_browser

HERE = Path(__file__).resolve().parent
APP = HERE / "electron"  # main.js・package.json


def electron() -> str | None:
    """Electron の実行ファイル。なければ None。"""
    chosen = os.environ.get("ECOBUILD_GUI_ELECTRON")
    if chosen:
        return chosen if Path(chosen).is_file() else None
    dist = HERE.parent / "electron" / "node_modules" / "electron" / "dist"
    names = {"win32": "electron.exe", "darwin": "Electron.app/Contents/MacOS/Electron"}
    found = dist / names.get(sys.platform, "electron")
    return str(found) if found.is_file() else None


def open_window(url: str, title: str, size: list[int]) -> None:
    if os.environ.get("GUIFRAMEWORK_NO_WINDOW"):  # 試験用：開かない（GUIFrameWork の既定と同じ）
        return
    exe = electron()
    if exe is None:
        open_in_browser(url, title, size)
        return
    env = {k: v for k, v in os.environ.items() if k != "ELECTRON_RUN_AS_NODE"}  # 付いていると、窓のアプリとして動かない
    flags = 0x08000000 if sys.platform == "win32" else 0  # コマンドプロンプトの窓を出さない
    try:
        subprocess.Popen([exe, str(APP), f"--url={url}", f"--title={title}", f"--size={size[0]}x{size[1]}"],
                         env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    except OSError:
        open_in_browser(url, title, size)
