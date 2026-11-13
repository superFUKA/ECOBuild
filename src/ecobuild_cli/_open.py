"""この PC の道具で、ファイル・フォルダーを開く（ecobuild open）。画面を開くのは CLI の関心なので、CLI に置く。

- explorer：フォルダーをファイルの管理の道具（Windows はエクスプローラー）で開く。ファイルなら、そのファイルを選んだ状態で開く。
- default：既定のアプリで開く（フォルダーなら、ファイルの管理の道具）。
- editor：開発の道具で開く（Visual Studio が使えればそれで、なければ既定のアプリで）。
- vs：Visual Studio で開く（Windows だけ）。フォルダーなら、その中のソリューション（ビルドで作られたもの。なければ
  フォルダーとして）。ファイルなら、そのフォルダーを開いている Visual Studio の窓で（なければ、ファイルだけを開く）。
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path

from ecobuild.errors import EcoBuildError, ErrorCode

APPS = ("default", "explorer", "editor", "vs")
VISUAL_STUDIO = {"2026": "[18.0,19.0)", "2022": "[17.0,18.0)"}  # 版の名前 → vswhere のバージョンの範囲（新しい順）


def _quiet() -> dict:
    """道具に問い合わせるとき、黒い窓を出さない（Windows）。"""
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def _windows() -> bool:
    return os.name == "nt"


def _start(line: list[str], cwd: Path | None = None) -> None:
    """道具を起こす（終わるのを待たない）。"""
    subprocess.Popen(line, cwd=str(cwd) if cwd else None)


def _start_default(target: Path) -> None:
    """既定のアプリで開く（Windows。フォルダーはエクスプローラー）。"""
    os.startfile(str(target))  # noqa: S606


def _vswhere() -> Path | None:
    base = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    path = Path(base) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    return path if path.is_file() else None


def visual_studio(version: str) -> str | None:
    """その版の Visual Studio の devenv.exe（vswhere で探す）。なければ None。"""
    vswhere, versions = _vswhere(), VISUAL_STUDIO.get(version)
    if not _windows() or vswhere is None or versions is None:
        return None
    completed = subprocess.run([str(vswhere), "-version", versions, "-prerelease", "-latest", "-property", "productPath"],
                               capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, **_quiet())
    path = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
    return path if path and Path(path).is_file() else None


def visual_studio_versions() -> list[str]:
    """この PC にある版（新しい順）。"""
    return [version for version in VISUAL_STUDIO if visual_studio(version)]


def find_solution(directory: Path) -> Path | None:
    """ビルドで作られた Visual Studio のソリューション（build/ の下。なければ、その場所の直下）。新しいものを選ぶ。"""
    found = [p for place in ("build/", "build/*/", "build/*/*/", "") for suffix in (".sln", ".slnx")
             for p in directory.glob(f"{place}*{suffix}")]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def unavailable(app: str, target: Path, vs_version: str = "") -> str:
    """今、その道具で開けない理由（開けるなら空の文字）。"""
    if not target.exists():
        return f"見つかりません：{target}"
    if app != "vs":
        return ""
    if not _windows():
        return "Visual Studio で開けるのは Windows だけです。"
    if vs_version:
        if visual_studio(vs_version):
            return ""
        others = [v for v in visual_studio_versions() if v != vs_version]
        return f"Visual Studio {vs_version} が、この PC に見つかりません。" + (f"あるのは {'・'.join(others)} です。" if others else "")
    return "" if visual_studio_versions() else "Visual Studio が、この PC に見つかりません。"


def open_with(app: str, target: Path, *, root: Path | None = None, vs_version: str = "", line: int = 0) -> dict:
    """開く（終わるのを待たない）。root：Visual Studio で開くときの、ソリューションを探す場所（モジュールのフォルダー）。"""
    if app == "editor" and target.exists():  # Visual Studio が使えればそれで、なければ既定のアプリで
        app = "default" if unavailable("vs", target, vs_version) else "vs"
    reason = unavailable(app, target, vs_version)
    if reason:
        if not target.exists():
            raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, reason)
        raise EcoBuildError(ErrorCode.TOOL_MISSING, reason, hint="--app default（既定のアプリ）か --app explorer でも開けます。")
    if app == "vs":
        return _open_in_visual_studio(target, root or (target if target.is_dir() else target.parent), vs_version, line)
    reveal = app == "explorer" and target.is_file()
    if _windows():
        if reveal:
            _start(["explorer", "/select,", str(target)])
        else:
            _start_default(target)
    elif sys.platform == "darwin":
        _start(["open", "-R", str(target)] if reveal else ["open", str(target)])
    else:
        _start(["xdg-open", str(target.parent if reveal else target)])
    return {"app": app, "path": target.as_posix(), "opened": "reveal" if reveal else "folder" if target.is_dir() else "file", "name": target.name}


def _open_in_visual_studio(target: Path, root: Path, version: str, line: int) -> dict:
    version = version or visual_studio_versions()[0]
    devenv = visual_studio(version)
    assert devenv is not None  # unavailable で確かめてある
    place = find_solution(root) or root  # ソリューション（なければ、フォルダーとして開く）
    result = {"app": "vs", "path": target.as_posix(), "version": version,
              "solution": None if place.is_dir() else place.as_posix(), "folder": place.as_posix() if place.is_dir() else None}
    if target.is_dir():
        _start([devenv, str(place)], place if place.is_dir() else place.parent)
        return {**result, "opened": "folder" if place.is_dir() else "solution", "name": place.name}
    # ファイル：そのソリューション・フォルダーを開いている窓があれば、そこで開く。なければ /edit（最後に使った窓か、新しい窓）
    if not _open_in_window(_processes(place), target, line):
        _start([devenv, "/edit", str(target), *(["/command", f"Edit.GoTo {line}"] if line > 0 else [])], target.parent)
    return {**result, "opened": "file", "line": line or None, "name": target.name}


def _processes(opened: Path) -> list[int]:
    """そのソリューション・フォルダーを開いている Visual Studio のプロセス番号（窓の題「<名前> - Microsoft Visual Studio」で見る）。"""
    name = opened.name if opened.is_dir() else opened.stem
    completed = subprocess.run(["tasklist", "/v", "/fi", "imagename eq devenv.exe", "/fo", "csv", "/nh"],
                               capture_output=True, encoding="mbcs", errors="replace", stdin=subprocess.DEVNULL, **_quiet())
    return [int(row[1]) for row in csv.reader(completed.stdout.splitlines())
            if len(row) > 2 and row[0].lower() == "devenv.exe" and row[1].isdigit()
            and row[-1].split(" - ")[0].strip().lower() == name.lower()]


# 実行中の Visual Studio（プロセス番号で選ぶ）の DTE を ROT（実行中のオブジェクトの表）から取り出す。PowerShell の Add-Type で使う。
# devenv /edit は「最後に使った Visual Studio」で開くため、ソリューションを開いた窓とは別の窓で開くことがある。
_VS_DTE = r"""
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
public static class EcoVs {
    [DllImport("ole32.dll")] static extern int GetRunningObjectTable(int reserved, out IRunningObjectTable table);
    [DllImport("ole32.dll")] static extern int CreateBindCtx(int reserved, out IBindCtx context);
    public static object Dte(int pid) {
        IRunningObjectTable table; IBindCtx context; IEnumMoniker monikers;
        if (GetRunningObjectTable(0, out table) != 0 || CreateBindCtx(0, out context) != 0) return null;
        table.EnumRunning(out monikers);
        IMoniker[] one = new IMoniker[1];
        while (monikers.Next(1, one, IntPtr.Zero) == 0) {
            string name;
            one[0].GetDisplayName(context, null, out name);
            if (name.StartsWith("!VisualStudio.DTE.") && name.EndsWith(":" + pid)) {
                object dte;
                table.GetObject(one[0], out dte);
                return dte;
            }
        }
        return null;
    }
}
"""

# 起動したばかりの Visual Studio は COM の呼び出しを断ることがある（RPC_E_CALL_REJECTED）ため、少し待って何度か試す。
_VS_OPEN_FILE = ("$ErrorActionPreference = 'Stop'; Add-Type -TypeDefinition $env:EG_CS; "
                 "foreach ($p in ($env:EG_PIDS -split ',')) { $dte = [EcoVs]::Dte([int]$p); if ($dte -eq $null) { continue }; "
                 "for ($i = 0; $i -lt 20; $i++) { try { [void]$dte.ItemOperations.OpenFile($env:EG_FILE); "
                 "if ([int]$env:EG_LINE -gt 0) { try { $dte.ActiveDocument.Selection.GotoLine([int]$env:EG_LINE) } catch {} }; "
                 "try { $dte.MainWindow.Activate() } catch {}; exit 0 } catch { Start-Sleep -Milliseconds 500 } } }; exit 1")


def _open_in_window(pids: list[int], target: Path, line: int) -> bool:
    """そのプロセスの Visual Studio の窓でファイルを開く（DTE の ItemOperations.OpenFile）。できなければ False。"""
    if not pids:
        return False
    completed = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _VS_OPEN_FILE],
                               env=dict(os.environ, EG_CS=_VS_DTE, EG_PIDS=",".join(map(str, pids)), EG_FILE=str(target), EG_LINE=str(line)),
                               stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8", errors="replace", **_quiet())
    return completed.returncode == 0
