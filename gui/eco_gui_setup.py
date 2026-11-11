"""新しい GUI（eco_gui）を使えるようにする：専用の venv に GUIFrameWork を入れ、ショートカットを作り、
拡張コマンド ecobuild gui の入口（ecobuild-gui）を置く。

インストーラーが呼ぶ。手でも実行できる：

    python eco_gui_setup.py                  # 既定の場所に venv、デスクトップとスタートメニューにショートカット、ecobuild gui の入口
    python eco_gui_setup.py --no-shortcuts   # ショートカットを作らない
    python eco_gui_setup.py --no-command     # ecobuild gui の入口を置かない

使うのは Python の標準ライブラリだけ（GUIFrameWork は、ここで作る venv に入れる）。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "ECOBuild GUI（新）"


def default_venv() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return base / "Programs" / "ECOBuild GUI Next" / "venv"


def python_of(venv: Path, windowless: bool = False) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / ("pythonw.exe" if windowless else "python.exe")
    return venv / "bin" / "python"


def prepare(venv: Path) -> None:
    """venv を作り（なければ）、eco_gui/requirements.txt の版の GUIFrameWork を入れる。"""
    if not python_of(venv).is_file():
        venv.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    requirements = HERE / "eco_gui" / "requirements.txt"
    wanted = requirements.read_text(encoding="utf-8")
    stamp = venv / "eco_gui-requirements.txt"  # 入れたときの requirements.txt の写し
    if stamp.is_file() and stamp.read_text(encoding="utf-8") == wanted:
        return
    # 入れるものは、ここで読んで引数で渡す（pip に -r で読ませると、日本語の注釈を端末の文字コードで読もうとして失敗する）
    wanted_lines = [line.strip() for line in wanted.splitlines() if line.strip() and not line.strip().startswith("#")]
    # 版の番号が同じでもコミットが違えば入れ直す（pip は、番号が同じだと入れ直さない）
    subprocess.run([str(python_of(venv)), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                    "--force-reinstall", *wanted_lines], check=True)
    stamp.write_text(wanted, encoding="utf-8")


def place_command(ecobuild: str | None, python: Path | None = None) -> Path | None:
    """ecobuild-gui（拡張コマンド `ecobuild gui` の入口）を、ecobuild と同じフォルダーに置く。置いた・もうあった場所を返す。

    中身は、この GUI の ecobuild_gui.py を python で呼ぶだけ（python を省くと今の Python。窓のない pythonw なら隣の python）。
    今までの GUI も、起動のたびに同じ名前で置く（自分の Python で）。呼ぶ先は同じ ecobuild_gui.py で、どちらの Python でも動くので、
    動く入口がもうあれば触らない（取り合わない）。ない・指す先（Python かスクリプト）がなくなっているときだけ置く。
    ecobuild が見つからない・書けないときは None（何もしない）。
    """
    if not ecobuild or not Path(ecobuild).exists():
        return None
    python = Path(python or sys.executable)
    if python.name.lower() == "pythonw.exe" and python.with_name("python.exe").is_file():
        python = python.with_name("python.exe")  # 端末に出力するので、窓のない pythonw ではなく python
    script = HERE / "ecobuild_gui.py"
    # ecobuild のある所（PATH の上）。リンク（pipx 等）はたどらない：たどった先は PATH にないことがある
    folder = Path(os.path.abspath(ecobuild)).parent
    if os.name == "nt":
        target, text = folder / "ecobuild-gui.cmd", f'@"{python}" "{script}" %*\r\n'
    else:
        target, text = folder / "ecobuild-gui", f'#!/bin/sh\nexec "{python}" "{script}" "$@"\n'
    try:
        if target.is_file():
            pointed = [p for p in re.findall(r'"([^"]+)"', target.read_text(encoding="utf-8", errors="replace")) if p != "$@"]
            if len(pointed) >= 2 and all(Path(p).is_file() for p in pointed):  # Python とスクリプト
                return target  # 動く入口がある（だれが置いたものでも）
        target.write_text(text, encoding="utf-8", newline="")
        if os.name != "nt":
            target.chmod(0o755)
        return target
    except OSError:
        return None


def shortcut_places() -> list[Path]:
    """デスクトップとスタートメニューのプログラムのフォルダ（OneDrive に移したデスクトップも Windows に尋ねる）。"""
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                           "[Console]::OutputEncoding = [Text.Encoding]::UTF8; [Environment]::GetFolderPath('Desktop'); "
                           "[Environment]::GetFolderPath('Programs')"],
                          capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    return [Path(line) for line in done.stdout.splitlines() if line.strip()]


def make_shortcut(place: Path, venv: Path) -> Path:
    """「その venv の pythonw で ECOBuildGUINext.pyw」を開くショートカット（.lnk）。値は環境変数で渡す（引用符の扱いを避ける）。"""
    link = place / f"{NAME}.lnk"
    script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:EG_LINK); $s.TargetPath = $env:EG_TARGET; "
              "$s.Arguments = $env:EG_ARGS; $s.WorkingDirectory = $env:EG_DIR; $s.IconLocation = $env:EG_ICON + ',0'; "
              "$s.Description = $env:EG_DESCRIPTION; $s.Save()")
    env = dict(os.environ, EG_LINK=str(link), EG_TARGET=str(python_of(venv, windowless=True)),
               EG_ARGS=subprocess.list2cmdline([str(HERE / "ECOBuildGUINext.pyw")]), EG_DIR=str(HERE),
               EG_ICON=str(HERE / "icon.ico"), EG_DESCRIPTION="ECOBuild GUI（GUIFrameWork の上の新しい GUI）")
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                          stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8", errors="replace")
    if done.returncode != 0 or not link.is_file():
        raise RuntimeError(f"ショートカットを作れませんでした：{link}\n{done.stderr.strip()}")
    return link


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="新しい GUI（eco_gui）を使えるようにする")
    parser.add_argument("--venv", default="", help="GUIFrameWork を入れる venv（既定：%%LOCALAPPDATA%%\\Programs\\ECOBuild GUI Next\\venv）")
    parser.add_argument("--shortcuts", nargs="*", default=None, help="ショートカットを置くフォルダー（既定：デスクトップとスタートメニュー）")
    parser.add_argument("--no-shortcuts", action="store_true", help="ショートカットを作らない")
    parser.add_argument("--ecobuild", default="", help="ecobuild の場所（ecobuild gui の入口を、その隣に置く。既定：PATH の ecobuild）")
    parser.add_argument("--no-command", action="store_true", help="ecobuild gui の入口（ecobuild-gui）を置かない")
    options = parser.parse_args(argv)
    venv = Path(options.venv) if options.venv else default_venv()
    try:
        prepare(venv)
        print(f"venv：{venv}")
        if not options.no_command:
            placed = place_command(options.ecobuild or shutil.which("ecobuild"), python_of(venv))
            print(f"ecobuild gui の入口：{placed}" if placed else "ecobuild gui の入口は置けませんでした（ecobuild が見つからないか、書けません）。")
        if not options.no_shortcuts and os.name == "nt":
            places = [Path(p) for p in options.shortcuts] if options.shortcuts is not None else shortcut_places()
            for place in places:
                if place.is_dir():
                    print(f"ショートカット：{make_shortcut(place, venv)}")
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"新しい GUI を準備できませんでした：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
