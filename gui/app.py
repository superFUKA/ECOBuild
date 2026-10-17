"""ECOBuildのGUI：画面（static/）を配り、画面からの依頼で ecobuild のCLIを実行する。

ECOBuildの実装（src/ のパッケージ）とは独立している。ECOBuildのコードは読み込まず、ecobuild コマンドを呼ぶだけ。
使うのは Python の標準ライブラリだけ（3.11 以上）。起動：python gui/app.py（または ECOBuildGUI.pyw をダブルクリック）

- 起動すると、Electron（electron/。npm install 済みのとき）でGUIの窓を開き、起動したコマンドはすぐ終わる。
  Electron は自分専用のサーバー（--electron）を子プロセスで動かし、窓をすべて閉じると両方とも終わる。
- Electron がなければ（または --browser）、窓のない Python（pythonw）でサーバーを裏で動かし、Edge の窓で開く。
  すでに動いていればそれを使い、更新前の古いサーバーなら入れ替える。GUIの窓がすべて閉じてしばらくすると、サーバーも終わる。
  端末で動かし続けるなら --foreground（開発用）。

- 待ち受けは 127.0.0.1 だけ。APIは起動ごとに作る合言葉（X-ECOBuild-Token）がなければ断る。
- CLIは `ecobuild -C <場所> <コマンド> --json` で実行し、出力のJSONをそのまま画面へ返す。
  ecobuild の場所：--ecobuild、環境変数 ECOBUILD_GUI_CLI（JSONの配列。開発用）、PATH、起動したPythonと
  同じ環境の Scripts（bin）の順に探す。ECOBuildのCLIはGUIの存在を知らない。
- CLIにない手元の処理（モジュールの一覧と専用のcloneの登録、ファイルの一覧、フォルダ・空のファイルの作成、
  既定のアプリで開く、フォルダの選択、ログイン中のアカウント名）だけをGUIが行う。登録の置き場所は ECOBUILD_GUI_HOME（既定は %APPDATA%/ecobuild-gui 等）の gui.json。
"""

from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import re
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

VERSION = "0.1.0"
# 起動した時の app.py。画面（static/）は毎回ファイルから配るが、サーバーのコードは起動した時のまま。
# app.py が後から変わったら、画面に「起動し直して」と出す（新しい画面の依頼をこのサーバーが知らないため）。
STARTED_WITH = Path(__file__).stat().st_mtime


def server_is_stale() -> bool:
    try:
        return Path(__file__).stat().st_mtime != STARTED_WITH
    except OSError:
        return False


STALE_MESSAGE = ("GUIが更新されました。GUIを起動し直すと新しい版に切り替わります（このウィンドウは閉じてください）。")
IDLE_SECONDS = int(os.environ.get("ECOBUILD_GUI_IDLE") or 180)  # 画面から連絡がこの秒数なければ、裏で動くサーバーは終わる（画面は20秒ごとに連絡する）
STATIC = Path(__file__).with_name("static")
MODULE_FILE = Path(".ecobuild") / "ecobuild.toml"   # モジュールの印（ECOBuildの共有の設定）
DEFAULT_PORT = 8765
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}

# 何も変えないコマンド（同じ場所で他のコマンドが動いていても待たずに実行する）。
# task next・task overdue・task workload・sprint status・milestone status は、読む前に GitHub から取得（git fetch）して
# 段階のずれを直すので、ここに入れない（同じ場所で並べて fetch すると、git の参照のロックがぶつかる）。
READ_ONLY = {
    ("status",), ("log",), ("show",), ("diff",), ("blame",), ("doctor",), ("module", "types"), ("module", "list"),
    ("module", "show"), ("module", "clones"), ("config", "list"), ("config", "get"), ("task", "list"), ("task", "status"),
    ("task", "diff"), ("branch", "list"), ("deps", "list"), ("deps", "tree"),
    ("project", "list"), ("profile", "list"), ("milestone", "list"), ("sprint", "list"), ("stash", "list"),
    ("ci", "status"), ("release", "list"),
    ("agent", "guide"), ("agent", "start"),   # agent start はファイルを変えず、画面を開いてすぐ戻る（ビルド中でも待たせない）
}
FETCHING = {("status",)}   # --fetch を付けると取得する（status --fetch は、名前が変わった origin も合わせる）


def _read_only(args: list[str]) -> bool:
    command = tuple(a for a in args[:2] if not a.startswith("-"))
    if "--fetch" in args and (command[:1] in FETCHING or command in FETCHING):
        return False
    return command in READ_ONLY or command[:1] in READ_ONLY


def _no_window() -> dict:
    """Windowsで子プロセスの黒い窓を出さない。"""
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


class Store:
    """GUIだけが使う記録。ファイルは gui.json。CLIから分かることは持たない（このPCにある作業空間は ecobuild workspace list、
    アーカイブ済みか等は module list に聞く）。持つのは、ハブの一覧の並び順だけ。"""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def order(self) -> list[str]:
        with self._lock:
            return list(self._load().get("order", []))

    def set_order(self, paths: list[str]) -> None:
        """一覧の並び（ハブでドラッグして並べ替えたもの）。"""
        with self._lock:
            data = self._load()
            data["order"] = [Path(p).as_posix() for p in paths]
            self._save(data)

    def take_legacy(self) -> tuple[list[str], list[str]]:
        """以前の gui.json が持っていた、一覧のフォルダ（modules）と専用のclone（workspaces）。取り出して消す
        （今は ecobuild workspace list の記録に入れる。一覧の並びは order に残す）。"""
        with self._lock:
            data = self._load()
            if "modules" not in data and "workspaces" not in data:
                return [], []
            modules = [item["path"] for item in data.pop("modules", []) if isinstance(item, dict) and "path" in item]
            workspaces = [d for items in data.pop("workspaces", {}).values() for d in items]
            data.setdefault("order", modules)
            self._save(data)
            return modules, workspaces


def _key(path: str | Path) -> str:
    return Path(path).resolve().as_posix().lower()


def _same(a: str | Path, b: str | Path) -> bool:
    return _key(a) == _key(b)


def _module_root(path: Path) -> Path:
    """ecobuild.toml のある場所（指定した場所か、その上）。"""
    path = path.expanduser().resolve()
    for candidate in (path, *path.parents):
        if (candidate / MODULE_FILE).is_file():
            return candidate
    raise GuiError(f"ECOBuildのモジュールではありません（ecobuild.toml がありません）：{path}")


class GuiError(Exception):
    pass


class Cli:
    """ecobuild のCLIを実行する。変える操作は場所ごとに1つずつ（gitの競合を避ける）。"""

    def __init__(self, command: list[str]):
        self.command = command
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock_for(self, directory: str | None) -> threading.Lock:
        key = _key(directory) if directory else ""
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def run(self, directory: str | None, args: list[str], stdin: str | None = None) -> dict:
        if not args or not all(isinstance(a, str) for a in args):
            raise GuiError("コマンドの指定が正しくありません。")
        if directory and not Path(directory).is_dir():
            raise GuiError(f"フォルダが見つかりません：{directory}")
        argv = list(self.command) + (["-C", directory] if directory else []) + args + ["--json"]
        lock = None if _read_only(args) else self._lock_for(directory)
        if lock:
            lock.acquire()
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", GIT_TERMINAL_PROMPT="0")
            completed = subprocess.run(argv, input=stdin or "", capture_output=True, encoding="utf-8",
                                       errors="replace", env=env, cwd=_working_directory(directory, args),
                                       **_no_window())
        finally:
            if lock:
                lock.release()
        document = _last_json(completed.stdout)
        if document is None:
            document = {"ok": False, "command": " ".join(args), "result": None, "notices": [],
                        "error": {"code": "gui_no_output",
                                  "message": "ecobuild の結果を読み取れませんでした。",
                                  "hint": None, "details": (completed.stdout + completed.stderr)[-20000:]}}
        document["exit_code"] = completed.returncode
        document["stderr"] = completed.stderr[-20000:]
        document["argv"] = ["ecobuild"] + (["-C", directory] if directory else []) + args + ["--json"]
        return document


def _last_json(text: str) -> dict | None:
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                return None
    return None


def _working_directory(directory: str | None, args: list[str]) -> str:
    """ecobuild を起動するフォルダ（場所は -C で渡すので、どこでもよい）。module delete --remove-workspaces・workspace close はその場所を消すので、親から
    起動する（ecobuild.exe・venv の python.exe は本体を子として動かす起動役で、起動したフォルダをつかんだままになる）。"""
    if not directory:
        return str(Path.home())
    removes = args[:2] in (["module", "delete"], ["workspace", "close"]) or (args[:2] == ["task", "finish"]
                                                                            and "--close-workspace" in args)
    return str(Path(directory).parent) if removes else directory


def default_cli(explicit: str = "") -> list[str]:
    """ecobuild コマンドの場所。"""
    if explicit:
        return [explicit]
    configured = os.environ.get("ECOBUILD_GUI_CLI")
    if configured:
        return json.loads(configured)
    # ユーザーのPC環境の ecobuild（PATH）。なければ、起動したPythonと同じ環境（.venv 等）のもの
    found = shutil.which("ecobuild")
    if found:
        return [found]
    scripts = Path(sys.executable).parent
    for name in ("ecobuild.exe", "ecobuild"):
        if (scripts / name).is_file():
            return [str(scripts / name)]
    raise SystemExit("ecobuild コマンドが見つかりません。--ecobuild <パス> で指定してください。")


def cli_warning(command: list[str]) -> str:
    """ecobuild が .cmd／.bat のときの注意。cmd.exe を通るため、改行のある値は1行目だけになり、
    %名前% は環境変数に置き換わる（コミットメッセージ・本文・コメント等）。.exe（pip・pipx 等）なら問題ない。"""
    if os.name == "nt" and Path(command[0]).suffix.lower() in (".cmd", ".bat"):
        return (f"ecobuild が {Path(command[0]).name} です。改行を含む入力は1行目だけになり、%名前% は環境変数に"
                "置き換わります。.exe の ecobuild（pip・pipx 等で入れたもの）を --ecobuild で指定してください。")
    return ""


def gui_home() -> Path:
    """GUIの記録の置き場所（ECOBuildのツールの設定とは別）。"""
    if os.environ.get("ECOBUILD_GUI_HOME"):
        return Path(os.environ["ECOBUILD_GUI_HOME"])
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "ecobuild-gui"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ecobuild-gui"


# 手元の処理（CLIにないもの） -------------------------------------------------------------------

def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-C", str(root), *args], capture_output=True, encoding="utf-8",
                               errors="replace", **_no_window())
    return completed.stdout if completed.returncode == 0 else ""


def list_files(directory: str) -> dict:
    """エクスプローラーの中身：gitの管理対象と未追跡のファイル（.gitignore の対象は除く）と、空のフォルダ。"""
    root = Path(directory).resolve()
    if not root.is_dir():
        raise GuiError(f"フォルダが見つかりません：{root}")
    files = sorted({f for f in _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")
                    if f})
    ignored = {d.rstrip("/") for d in _git(root, "ls-files", "-z", "--others", "--ignored", "--exclude-standard",
                                          "--directory").split("\0") if d.endswith("/")}
    dirs: set[str] = set()
    for f in files:
        parts = f.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    for current, subdirs, _ in os.walk(root):
        relative = Path(current).relative_to(root).as_posix()
        relative = "" if relative == "." else relative
        keep = []
        for name in subdirs:
            path = f"{relative}/{name}" if relative else name
            if name == ".git" or path in ignored:
                continue
            keep.append(name)
            dirs.add(path)
        subdirs[:] = keep
    missing = [f for f in files if not (root / f).exists()]
    generated = [f for f in files if _is_generated(root / f)]
    return {"root": root.as_posix(), "files": files, "dirs": sorted(dirs), "missing": missing, "generated": generated}


def _is_generated(path: Path) -> bool:
    """ツールが作り、書き戻すファイル（CppBuild の CMakeLists.txt 等）。先頭の「Generated by … Do not edit」の印で見る。"""
    if path.suffix.lower() not in (".txt", ".cmake") or not path.is_file():
        return False
    try:
        with path.open("rb") as file:
            head = file.read(200).decode("utf-8", "replace")
    except OSError:
        return False
    return "Generated by" in head and "Do not edit" in head


def _inside(directory: str, relative: str) -> Path:
    root = Path(directory).resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise GuiError("この場所の外は指定できません。")
    if ".git" in target.relative_to(root).parts:
        raise GuiError(".git の中は操作できません。")
    return target


def make_directory(directory: str, relative: str) -> dict:
    target = _inside(directory, relative)
    if target.exists():
        raise GuiError(f"すでに存在します：{relative}")
    target.mkdir(parents=True)
    return {"path": target.relative_to(Path(directory).resolve()).as_posix()}


def module_defaults(directory: str) -> dict:
    """画面に既定値を入れておくための、モジュールの設定の一部（ecobuild.toml）。ecobuild にこれを返すコマンドがないため、
    GUIが読む。読めなければ空（画面は既定値を入れないだけ）。

    type：モジュールの型（画面に出す操作を型のコマンドに合わせる。module show にもあるが、GitHubを読むので待たせる）。"""
    import tomllib
    try:
        data = tomllib.loads((_module_root(Path(directory)) / MODULE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError, GuiError):
        return {}
    table = lambda name: data.get(name) if isinstance(data.get(name), dict) else {}
    found = {"type": table("module").get("type"), "default_base": table("branches").get("default_base")}
    return {key: value for key, value in found.items() if isinstance(value, str) and value}


def find_solution(directory: str) -> Path | None:
    """ビルドで作られた Visual Studio のソリューション（build/ の下。なければ場所の直下）。新しいものを選ぶ。
    VS 2022 のジェネレーターは .sln、VS 2026 のジェネレーターは .slnx を作る。"""
    root = Path(directory).resolve()
    found = [p for place in ("build/", "build/*/", "build/*/*/", "") for suffix in (".sln", ".slnx")
             for p in root.glob(f"{place}*{suffix}")]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


VISUAL_STUDIO = {"2026": "[18.0,19.0)", "2022": "[17.0,18.0)"}   # 名前 → vswhere のバージョンの範囲


def _vswhere() -> Path | None:
    base = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    path = Path(base) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    return path if path.is_file() else None


def _visual_studio(version: str) -> str | None:
    """その版の Visual Studio の devenv.exe（vswhere で探す）。"""
    vswhere, versions = _vswhere(), VISUAL_STUDIO.get(version)
    if vswhere is None or versions is None:
        return None
    completed = subprocess.run([str(vswhere), "-version", versions, "-prerelease", "-latest", "-property", "productPath"],
                               capture_output=True, encoding="utf-8", errors="replace", **_no_window())
    path = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
    return path if path and Path(path).is_file() else None


def visual_studio_versions() -> list[str]:
    """このPCにある版（画面の選択に使う）。"""
    return [version for version in VISUAL_STUDIO if _visual_studio(version)]


def open_in_visual_studio(directory: str, version: str = "2026") -> dict:
    """ソリューションを選んだ版の Visual Studio で開く。ソリューションがなければ {"solution": None}（画面がビルドを勧める）。
    ecobuild にこれを行うコマンドはないため、GUIが行う。"""
    if version not in VISUAL_STUDIO:
        raise GuiError(f"対応していない Visual Studio の版です：{version}")
    solution = find_solution(directory)
    if solution is None:
        return {"solution": None}
    devenv = _visual_studio(version)
    if not devenv:
        others = [v for v in visual_studio_versions() if v != version]
        raise GuiError(f"Visual Studio {version} が見つかりません。"
                       + (f"このPCにあるのは {'・'.join(others)} です。「VS〜で開く」の横の ▾ で切り替えてください。" if others else ""))
    subprocess.Popen([devenv, str(solution)], cwd=str(solution.parent))
    return {"solution": solution.as_posix(), "devenv": devenv, "version": version}


def _solution_is_open(solution: Path) -> bool:
    """そのソリューションを開いている Visual Studio があるか（ウィンドウの題名「<ソリューション名> - Microsoft Visual Studio」で見る。
    同じ名前のソリューションは見分けられない）。"""
    if os.name != "nt":
        return False
    completed = subprocess.run(["tasklist", "/v", "/fi", "imagename eq devenv.exe", "/fo", "csv", "/nh"],
                               capture_output=True, encoding="mbcs", errors="replace", **_no_window())
    for row in csv.reader(completed.stdout.splitlines()):
        if row and row[0].lower() == "devenv.exe" and row[-1].split(" - ")[0].strip().lower() == solution.stem.lower():
            return True
    return False


def open_file_in_visual_studio(directory: str, relative: str, version: str = "2026") -> dict:
    """ファイルを Visual Studio で開く。このモジュールのソリューションを開いた Visual Studio があればそこで（/edit）、
    なければソリューションを開いて起動し、そのウィンドウが出てからファイルを開く（/edit）。ソリューションがまだなければ
    ファイルだけを開く。Visual Studio がなければ GuiError（画面は既定のアプリで開く）。
    起動と同時に /command File.OpenFile を渡すと、起動途中で実行されてエラーになることがあるため使わない。"""
    if version not in VISUAL_STUDIO:
        raise GuiError(f"対応していない Visual Studio の版です：{version}")
    target = _inside(directory, relative)
    if not target.is_file():
        raise GuiError(f"ファイルが見つかりません：{relative}")
    devenv = _visual_studio(version)
    if not devenv:
        raise GuiError(f"Visual Studio {version} が見つかりません。")
    solution = find_solution(directory)
    if solution is not None and not _solution_is_open(solution):
        subprocess.Popen([devenv, str(solution)], cwd=str(solution.parent))
        threading.Thread(target=_edit_when_open, args=(devenv, solution, target), daemon=True).start()
        return {"started": True, "solution": solution.as_posix()}
    subprocess.Popen([devenv, "/edit", str(target)], cwd=str(target.parent))
    return {"started": False, "solution": solution.as_posix() if solution else None}


def _edit_when_open(devenv: str, solution: Path, target: Path, timeout: float = 180, interval: float = 1) -> bool:
    """起動した Visual Studio のウィンドウにソリューションが出たら、ファイルを開く（/edit）。出なければ何もしない。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _solution_is_open(solution):
            subprocess.Popen([devenv, "/edit", str(target)], cwd=str(target.parent))
            return True
        time.sleep(interval)
    return False


def make_file(directory: str, relative: str) -> dict:
    """空のファイルを作る（型が ecobuild file add に対応しないとき：generic 等）。"""
    target = _inside(directory, relative)
    if target.exists():
        raise GuiError(f"すでに存在します：{relative}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    return {"path": target.relative_to(Path(directory).resolve()).as_posix()}


def move_file(directory: str, source: str, destination: str) -> dict:
    """ファイルを移す・名前を変える（型が ecobuild file move に対応しないとき：generic 等）。"""
    origin, target = _inside(directory, source), _inside(directory, destination)
    if not origin.is_file():
        raise GuiError(f"見つかりません：{source}")
    if target.exists():
        raise GuiError(f"すでに存在します：{destination}")
    target.parent.mkdir(parents=True, exist_ok=True)
    origin.rename(target)
    return {"paths": [target.relative_to(Path(directory).resolve()).as_posix()]}


def remove_file(directory: str, relative: str) -> dict:
    """ファイルを消す（型が ecobuild file remove に対応しないとき：generic 等）。"""
    target = _inside(directory, relative)
    if not target.is_file():
        raise GuiError(f"見つかりません：{relative}")
    target.unlink()
    return {"paths": [target.relative_to(Path(directory).resolve()).as_posix()]}


def make_parent(path: str) -> dict:
    """モジュールの作成・取得の前に、置き場所（親のフォルダ）を用意する。"""
    target = Path(path).expanduser()
    if not target.is_absolute():
        raise GuiError("置き場所は絶対パスで指定してください。")
    target.mkdir(parents=True, exist_ok=True)
    return {"path": target.resolve().as_posix()}


def open_path(directory: str, relative: str, reveal: bool) -> dict:
    target = _inside(directory, relative or ".")
    if not target.exists():
        raise GuiError(f"見つかりません：{relative}")
    if os.name == "nt":
        if reveal and target.is_file():
            subprocess.Popen(["explorer", "/select,", str(target)])
        else:
            os.startfile(str(target))  # noqa: S606（既定のアプリで開く）
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R" if reveal else "", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target.parent if reveal else target)])
    return {}


def read_text(directory: str, relative: str) -> dict:
    target = _inside(directory, relative)
    if not target.is_file():
        raise GuiError(f"ファイルが見つかりません：{relative}")
    data = target.read_bytes()[:400_000]
    if b"\0" in data[:8000]:
        return {"binary": True, "text": ""}
    return {"binary": False, "text": data.decode("utf-8", errors="replace"), "truncated": target.stat().st_size > len(data)}


_PICK = r"""
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk(); root.overrideredirect(True); root.geometry("0x0+0+0"); root.attributes("-topmost", True)
root.lift(); root.focus_force()   # a withdrawn owner leaves the picker behind the GUI window
path = filedialog.askdirectory(parent=root, title=sys.argv[1], initialdir=sys.argv[2] or None, mustexist=False)
print(path or "")
"""


def pick_folder(title: str, initial: str) -> dict:
    """フォルダを選ぶ窓（OSの標準）。選ばなければ空。"""
    completed = subprocess.run([sys.executable, "-c", _PICK, title or "フォルダを選ぶ", initial or ""],
                               capture_output=True, encoding="utf-8", errors="replace")
    return {"path": completed.stdout.strip()}


_me: dict = {}


def who_am_i() -> str:
    """ログイン中のGitHubのアカウント（画面で「自分」を示すため）。ecobuild にこれを返すコマンドはない。"""
    if "login" not in _me:
        try:
            completed = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True,
                                       encoding="utf-8", errors="replace", timeout=20, **_no_window())
            _me["login"] = completed.stdout.strip() if completed.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            _me["login"] = ""
    return os.environ.get("ECOBUILD_GUI_ME") or _me["login"]


def module_repository(directory: str) -> str:
    """モジュールの GitHub のリポジトリ（所有者/名前）。ecobuild module delete に渡す。origin の URL から読む（ecobuild にこれを返す
    コマンドはない）。GitHub の URL でなければ（手元の bare 等）名前だけ。読めなければ空。"""
    url = _git(Path(directory), "remote", "get-url", "origin").strip()
    if not url:
        return ""
    match = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return re.sub(r"\.git$", "", re.split(r"[\\/]", url.rstrip("/\\"))[-1])


GH_SCOPES = {"delete_repo", "project"}   # 画面から追加を頼める gh の権限


def refresh_scope(scope: str) -> None:
    """gh のログインに権限を足す（gh auth refresh。ブラウザで承認する）。対話が要るので、新しい端末の窓で動かす。"""
    if scope not in GH_SCOPES:
        raise GuiError(f"対応していない権限です：{scope}")
    if os.name != "nt":
        raise GuiError(f"ターミナルで gh auth refresh -h github.com -s {scope} を実行してください。")
    subprocess.Popen(["cmd", "/c", f"gh auth refresh -h github.com -s {scope} & pause"],
                     creationflags=subprocess.CREATE_NEW_CONSOLE)


# HTTP --------------------------------------------------------------------------------------------

class App:
    def __init__(self, cli: Cli, store: Store, token: str, port: int):
        self.cli, self.store, self.token, self.port = cli, store, token, port
        self.last_contact = time.monotonic()
        self.server: ThreadingHTTPServer | None = None

    def move_legacy(self) -> None:
        """以前の gui.json に登録したフォルダを、ecobuild の作業空間の記録（workspace add）へ移す（一度だけ）。"""
        modules, workspaces = self.store.take_legacy()
        for path in modules + workspaces:
            if (Path(path) / MODULE_FILE).is_file():
                self.cli.run(None, ["workspace", "add", path])

    def api(self, name: str, body: dict) -> object:
        d = body.get
        if name == "cli":
            return self.cli.run(d("dir") or None, list(d("args") or []), d("stdin"))
        if name == "ping":
            return {"version": VERSION, "stale": STALE_MESSAGE if server_is_stale() else "", "pid": os.getpid()}
        if name == "shutdown":
            if self.server is not None:
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            return {}
        if name == "info":
            return {"me": who_am_i(), "cli": self.cli.command, "cli_warning": cli_warning(self.cli.command),
                    "stale": STALE_MESSAGE if server_is_stale() else "",
                    "home": str(Path.home()),
                    "version": VERSION}
        if name == "modules/order":
            if d("paths") is None:
                return self.store.order()
            self.store.set_order(list(d("paths")))
            return {}
        if name == "files":
            return list_files(d("dir"))
        if name == "mkdir":
            return make_directory(d("dir"), d("path"))
        if name == "module-defaults":
            return module_defaults(d("dir"))
        if name == "open-vs":
            return open_in_visual_studio(d("dir"), d("version") or "2026")
        if name == "open-file-vs":
            return open_file_in_visual_studio(d("dir"), d("path"), d("version") or "2026")
        if name == "vs-versions":
            return visual_studio_versions()
        if name == "touch":
            return make_file(d("dir"), d("path"))
        if name == "move-file":
            return move_file(d("dir"), d("source"), d("destination"))
        if name == "remove-file":
            return remove_file(d("dir"), d("path"))
        if name == "mkparent":
            return make_parent(d("path"))
        if name == "shortcut":
            return {"made": make_shortcuts()}
        if name == "module-repository":
            return {"repository": module_repository(d("dir"))}
        if name == "gh-scope":
            refresh_scope(d("scope") or "")
            return {}
        if name == "open-window":
            # GUIの別の画面（モジュールの窓）を、ハブと同じアプリの窓で開く（画面の window.open では普通のタブになるため）。
            page = d("page") or ""
            if not page.startswith(("module.html?", "hub.html")) or "//" in page or "\\" in page.split("?")[0]:
                raise GuiError("この画面は開けません。")
            separator = "&" if "?" in page else "?"
            open_window(f"http://127.0.0.1:{self.port}/{page}{separator}t={self.token}")
            return {}
        if name == "open":
            return open_path(d("dir"), d("path") or "", bool(d("reveal")))
        if name == "read":
            return read_text(d("dir"), d("path"))
        if name == "pick-folder":
            return pick_folder(d("title") or "", d("initial") or "")
        raise GuiError(f"不明な操作です：{name}" + (f"。{STALE_MESSAGE}" if server_is_stale() else
                                                    "。GUIのサーバーが画面より古い可能性があります。GUIを起動し直してください。"))


def make_handler(app: App):
    allowed_hosts = {f"127.0.0.1:{app.port}", f"localhost:{app.port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "ECOBuildGUI"

        def log_message(self, format, *args):  # 端末を静かに保つ
            pass

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, value: object) -> None:
            self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            if self.headers.get("Host") not in allowed_hosts:
                return self._send(HTTPStatus.FORBIDDEN, b"forbidden", "text/plain")
            path = urlparse(self.path).path
            if path == "/":
                path = "/hub.html"
            target = (STATIC / path.lstrip("/")).resolve()
            if STATIC.resolve() not in target.parents or not target.is_file():
                return self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
            # Windowsのレジストリの関連付けに左右されないよう、配るものの種類は決めておく
            content_type = CONTENT_TYPES.get(target.suffix) or mimetypes.guess_type(target.name)[0] \
                or "application/octet-stream"
            self._send(HTTPStatus.OK, target.read_bytes(), content_type)

        def do_POST(self):
            if self.headers.get("Host") not in allowed_hosts or \
                    not secrets.compare_digest(self.headers.get("X-ECOBuild-Token", ""), app.token):
                return self._json(HTTPStatus.FORBIDDEN, {"error": "認証に失敗しました。GUIを開き直してください。"})
            app.last_contact = time.monotonic()
            path = urlparse(self.path).path
            if not path.startswith("/api/"):
                return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                self._json(HTTPStatus.OK, {"value": app.api(path[len("/api/"):], body)})
            except GuiError as error:
                self._json(HTTPStatus.OK, {"error": str(error)})
            except Exception as error:  # 画面に理由を出す（サーバーは止めない）
                self._json(HTTPStatus.OK, {"error": f"{type(error).__name__}: {error}"})

    return Handler


class Server(ThreadingHTTPServer):
    """使われているポートでは待ち受けない（Windows は再利用の設定だと同じポートを二重に取れてしまう）。"""
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def _edge() -> str | None:
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            candidate = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if candidate.is_file():
                return str(candidate)
    return shutil.which("msedge")


HUB_WINDOW = (1000, 720)   # ハブは一覧と設定だけなので小さめ（hub.js も最初に開いたときこの大きさに合わせる）


def open_window(url: str, size: tuple[int, int] | None = None) -> None:
    """Edgeがあればアプリのウィンドウ（アドレスバーなし）で、なければ既定のブラウザで開く。size：最初の大きさ。"""
    edge = _edge() if os.name == "nt" else None
    if edge:
        subprocess.Popen([edge, f"--app={url}", *([f"--window-size={size[0]},{size[1]}"] if size else [])])
    else:
        webbrowser.open(url)


def _state_file() -> Path:
    return gui_home() / "server.json"


def _read_state() -> dict | None:
    try:
        return json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _ping(state: dict | None) -> dict | None:
    """動いているサーバーに尋ねる（合言葉が合い、応答があれば内容を返す）。"""
    if not state:
        return None
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{state['port']}/api/ping", data=b"{}", method="POST",
                                         headers={"X-ECOBuild-Token": state["token"], "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.loads(response.read()).get("value")
    except (OSError, ValueError, KeyError):
        return None


def _shutdown(state: dict) -> None:
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{state['port']}/api/shutdown", data=b"{}", method="POST",
                                         headers={"X-ECOBuild-Token": state["token"]})
        urllib.request.urlopen(request, timeout=3).close()
    except OSError:
        pass


def _url(state: dict) -> str:
    return f"http://127.0.0.1:{state['port']}/hub.html?t={state['token']}"


def _say(message: str) -> None:
    """端末があれば表示し、なければ（ダブルクリックで起動）エラーだけ窓で知らせる。"""
    if sys.stdout is not None:
        try:
            print(message, flush=True)
            return
        except (OSError, ValueError):
            pass


def _alert(message: str) -> None:
    if sys.stdout is not None:
        _say(message)
    elif os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "ECOBuild GUI", 0x10)


def _shortcut_places() -> list[Path]:
    """デスクトップとスタートメニューのプログラムのフォルダ（OneDrive に移したデスクトップも Windows に尋ねる）。"""
    completed = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                "[Console]::OutputEncoding = [Text.Encoding]::UTF8; [Environment]::GetFolderPath('Desktop'); [Environment]::GetFolderPath('Programs')"],
                               capture_output=True, encoding="utf-8", errors="replace", **_no_window())
    return [Path(line) for line in completed.stdout.splitlines() if line.strip()]


def make_shortcuts(places: list[Path] | None = None) -> list[str]:
    """デスクトップとスタートメニューに「ECOBuild GUI」のショートカット（アイコン付き）を作る。Windowsだけ。"""
    if os.name != "nt":
        raise GuiError("ショートカットは Windows でのみ作成できます。")
    here = Path(__file__).resolve().parent
    places = _shortcut_places() if places is None else places
    made = []
    for place in places:
        if not place.is_dir():
            continue
        link = place / "ECOBuild GUI.lnk"
        # .lnk は COM（WScript.Shell）で作る。値は環境変数で渡す（引用符の扱いを避ける）。
        script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:EG_LINK); $s.TargetPath = $env:EG_TARGET; "
                  "$s.Arguments = '\"' + $env:EG_SCRIPT + '\"'; $s.WorkingDirectory = $env:EG_DIR; "
                  "$s.IconLocation = $env:EG_ICON + ',0'; $s.Description = 'ECOBuild GUI'; $s.Save()")
        env = dict(os.environ, EG_LINK=str(link), EG_TARGET=_pythonw(), EG_SCRIPT=str(here / "ECOBuildGUI.pyw"),
                   EG_DIR=str(here), EG_ICON=str(here / "icon.ico"))
        completed = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                                   capture_output=True, encoding="utf-8", errors="replace", **_no_window())
        if completed.returncode != 0 or not link.is_file():
            raise GuiError(f"ショートカットを作成できませんでした：{link}\n{completed.stderr.strip()}")
        made.append(str(link))
    return made


def _pythonw() -> str:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate) if os.name == "nt" and candidate.is_file() else sys.executable


ELECTRON_APP = Path(__file__).resolve().with_name("electron")


def _electron() -> Path | None:
    """electron/ に入れた Electron（cd gui/electron; npm install）。なければ None。"""
    name = "electron.exe" if os.name == "nt" else "electron"
    candidate = ELECTRON_APP / "node_modules" / "electron" / "dist" / name
    return candidate if candidate.is_file() else None


def _found_cli(args) -> str | None:
    """ecobuild をここ（この端末の PATH）で探す。見つからなければ今知らせて終わる。サーバーに渡す場所（なければ None）を返す。"""
    try:
        found = default_cli(args.ecobuild)
    except SystemExit as error:
        _alert(str(error))
        sys.exit(1)
    return found[0] if len(found) == 1 and not os.environ.get("ECOBUILD_GUI_CLI") else None


def _start_detached(command: list[str], env: dict | None = None, no_window: bool = False) -> subprocess.Popen:
    """起動したコマンドが終わっても動き続けるように、切り離して起動する。"""
    streams = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        if no_window:
            flags |= subprocess.CREATE_NO_WINDOW
        return subprocess.Popen(command, env=env, creationflags=flags, close_fds=True, **streams)
    return subprocess.Popen(command, env=env, start_new_session=True, **streams)


def launch_electron(electron: Path, args) -> None:
    """Electron の窓で開き、すぐ終わる。すでに動いていれば、動いている方がハブの窓を開く。
    サーバーは Electron が起動する（URLを標準出力で受け取るので、pythonw ではなく python）。"""
    ecobuild = _found_cli(args)
    python = Path(sys.executable).with_name("python.exe") if os.name == "nt" else Path(sys.executable)
    env = dict(os.environ, ECOBUILD_GUI_PYTHON=str(python if python.is_file() else sys.executable))
    env.pop("ELECTRON_RUN_AS_NODE", None)   # 設定されていると Electron が Node として動き、窓を出さない
    if ecobuild:
        env["ECOBUILD_GUI_ECOBUILD"] = ecobuild
    _start_detached([str(electron), str(ELECTRON_APP)], env=env)
    _say("ECOBuild GUI を開きました（Electron）。")


def launch(args) -> None:
    """窓を開き、すぐ終わる。Electron があればそれで、なければ裏でサーバーを動かして Edge の窓で開く
    （動いているサーバーがあれば使い、古ければ入れ替える）。"""
    electron = None if args.browser or args.no_browser else _electron()
    if electron:
        launch_electron(electron, args)
        return
    state = _read_state()
    alive = _ping(state)
    if alive and not alive.get("stale"):
        if not args.no_browser:
            open_window(_url(state), HUB_WINDOW)
        _say(f"ECOBuild GUI を開きました（動いているサーバーを使います）：{_url(state)}")
        return
    old_token = (state or {}).get("token")
    if alive:   # 更新前のサーバー：止めてから新しく起動する
        _shutdown(state)
        time.sleep(1)
    # Find ecobuild here (with this terminal's PATH) so a missing one is reported now, and the server uses the same one.
    ecobuild = _found_cli(args)
    command = [_pythonw(), str(Path(__file__).resolve()), "--serve", "--port", str(args.port)]
    if ecobuild:
        command += ["--ecobuild", ecobuild]
    if args.no_browser:
        command.append("--no-browser")
    process = _start_detached(command, no_window=True)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        # The new server is the one with a new token (not the pid: a venv's pythonw starts the real Python as a child).
        state = _read_state()
        if state and state.get("token") != old_token and _ping(state):
            _say(f"ECOBuild GUI を起動しました：{_url(state)}\n（バックグラウンドで動いています。GUIのウィンドウをすべて閉じると、しばらくして終了します）")
            return
        if process.poll() is not None:
            break
        time.sleep(0.2)
    _alert(f"ECOBuild GUI を起動できませんでした。ログ：{gui_home() / 'gui.log'}")
    sys.exit(1)


def _end_when_idle(server, app) -> None:
    """--serve：画面から連絡がなくなったら（窓がすべて閉じたら）終わる。"""
    def watch():
        while True:
            time.sleep(15)
            if time.monotonic() - app.last_contact > IDLE_SECONDS:
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 開いている画面がないため終了します")
                server.shutdown()
                return
    threading.Thread(target=watch, daemon=True).start()


def _end_with_parent(server) -> None:
    """--electron：標準入力が閉じたら（Electron が終わったら）終わる。"""
    def watch():
        try:
            sys.stdin.read()
        except (OSError, ValueError):
            pass
        server.shutdown()
    threading.Thread(target=watch, daemon=True).start()


def serve(args) -> None:
    """サーバー本体。動き方は3通り。
    --serve：裏で動く（Edge の窓）。出力は記録に書き、画面から連絡がなくなったら終わる。
    --electron：Electron の子プロセス。URLを標準出力で Electron に伝え（窓は Electron が開く）、Electron と一緒に終わる。
    --foreground：端末で動く（開発用）。Ctrl+C で終わる。"""
    if args.serve:
        # 窓がないので、エラーは記録に書く。
        gui_home().mkdir(parents=True, exist_ok=True)
        log = open(gui_home() / "gui.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    else:
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(errors="replace")
    cli = Cli(default_cli(args.ecobuild))
    store = Store(gui_home() / "gui.json")
    token = secrets.token_urlsafe(24)
    try:
        server = Server(("127.0.0.1", args.port), None)
    except OSError:
        server = Server(("127.0.0.1", 0), None)
    port = server.server_address[1]
    app = App(cli, store, token, port)
    app.server = server
    app.move_legacy()
    server.RequestHandlerClass = make_handler(app)
    state = {"pid": os.getpid(), "port": port, "token": token}
    url = _url(state)
    if args.serve:
        _state_file().parent.mkdir(parents=True, exist_ok=True)
        _state_file().write_text(json.dumps(state), encoding="utf-8")
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 起動：{url}（ecobuild：{' '.join(cli.command)}）")
        _end_when_idle(server, app)
    elif args.electron:
        print(f"ECOBuild GUI：{url}", flush=True)   # electron/main.js がこの行からURLを読む
        _end_with_parent(server)
    else:
        print(f"ECOBuild GUI：{url}")
        print(f"ecobuild：{' '.join(cli.command)}")
        print("終了するには Ctrl+C を押してください。", flush=True)
    if cli_warning(cli.command):
        print("注意：" + cli_warning(cli.command), flush=True)
    if not args.no_browser and not args.electron:
        open_window(url, HUB_WINDOW)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if args.serve and (_read_state() or {}).get("pid") == os.getpid():
            try:
                _state_file().unlink()
            except OSError:
                pass


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ecobuild-gui", description="ECOBuildのGUIを開きます。")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"待ち受けるポート（既定 {DEFAULT_PORT}。"
                                                                       "使われていれば空いているもの）")
    parser.add_argument("--no-browser", action="store_true", help="ウィンドウを開かない（URLを表示するだけ）")
    parser.add_argument("--ecobuild", default="", help="ecobuild コマンドの場所（既定：PATH、なければ起動したPythonの環境）")
    parser.add_argument("--foreground", action="store_true", help="バックグラウンドで動かさず、このターミナルでサーバーを動かす（Ctrl+C で終了。開発用）")
    parser.add_argument("--shortcut", action="store_true",
                        help="デスクトップとスタートメニューにショートカット（アイコン付き）を作って終わる")
    parser.add_argument("--browser", action="store_true",
                        help="Electron があっても使わず、Edge（なければ既定のブラウザ）の窓で開く")
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)   # 裏で動くサーバー（launch が使う）
    parser.add_argument("--electron", action="store_true", help=argparse.SUPPRESS)  # Electron の子プロセス（electron/main.js が使う）
    args = parser.parse_args(argv)
    if args.shortcut:
        try:
            _say("作りました：\n" + "\n".join(make_shortcuts()))
        except GuiError as error:
            _alert(str(error))
            sys.exit(1)
    elif args.serve or args.foreground or args.electron:
        serve(args)
    else:
        launch(args)


if __name__ == "__main__":
    main()
