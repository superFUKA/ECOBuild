"""インストーラー（Setup.exe）がインストール・アンインストールの最後に、同梱の Python で実行する。

- install <入れた場所>：同梱の wheel から ecobuild を同梱の Python に入れ、<入れた場所>\\bin\\ecobuild.exe を置き、
  bin をユーザーの PATH に足す（端末・AI エージェントからも ecobuild が使える）。
- uninstall <入れた場所>：bin をユーザーの PATH から外す（ファイルはアンインストーラーが消す）。
"""
import ctypes
import shutil
import subprocess
import sys
import winreg
from pathlib import Path

RESOURCES = Path(__file__).resolve().parent.parent   # <入れた場所>\resources


def _user_path() -> tuple[list[str], int]:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        try:
            value, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            value, kind = "", winreg.REG_EXPAND_SZ
    return [entry for entry in value.split(";") if entry], kind


def _set_user_path(entries: list[str], kind: int) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "Path", 0, kind, ";".join(entries))
    # 開いているエクスプローラー等に知らせる（新しく開いた端末に効く）
    HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x001A, 0x0002
    ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000,
                                             ctypes.byref(ctypes.c_ulong()))


def _same(a: str, b: str) -> bool:
    return a.rstrip("\\/").lower() == b.rstrip("\\/").lower()


def install(home: Path) -> None:
    wheels = RESOURCES / "wheels"
    pip = next(wheels.glob("pip-*.whl"))
    subprocess.run([sys.executable, str(pip / "pip"), "install", "--no-index", "--find-links", str(wheels), "--upgrade",
                    "--no-warn-script-location", "--disable-pip-version-check", "--quiet", "ecobuild"], check=True)
    bin_dir = home / "bin"
    bin_dir.mkdir(exist_ok=True)
    # ecobuild.exe は Python の場所を中に持つので、別のフォルダに写しても動く（Scripts には pip 等もあるので PATH に出さない）
    shutil.copy2(Path(sys.executable).parent / "Scripts" / "ecobuild.exe", bin_dir / "ecobuild.exe")
    entries, kind = _user_path()
    if not any(_same(entry, str(bin_dir)) for entry in entries):
        _set_user_path(entries + [str(bin_dir)], kind)
    print(f"ecobuild を入れました：{bin_dir / 'ecobuild.exe'}")


def uninstall(home: Path) -> None:
    entries, kind = _user_path()
    kept = [entry for entry in entries if not _same(entry, str(home / "bin"))]
    if kept != entries:
        _set_user_path(kept, kind)


if __name__ == "__main__":
    action, home = sys.argv[1], Path(sys.argv[2])
    {"install": install, "uninstall": uninstall}[action](home)
