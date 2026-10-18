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
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import urllib.parse

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
sys.path.insert(0, str(Path(__file__).parent))
import actions as gui_actions  # noqa: E402（GUIの操作の一覧。ecobuild_gui.py も使う）
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


# 覚えておく読むだけのコマンド（GitHubに問い合わせて秒単位でかかるもの等）。画面は覚えた結果をすぐ出し、同時に読み直す
# （stale-while-revalidate：QueryCache）。変える操作を実行したら、覚えた結果はすべて「古い」にする（出してから読み直す）。
CACHEABLE = {
    ("task", "list"), ("task", "status"), ("task", "next"), ("task", "overdue"), ("task", "workload"),
    ("sprint", "list"), ("sprint", "status"), ("milestone", "list"), ("milestone", "status"),
    ("module", "show"), ("module", "list"), ("module", "settings"), ("branch", "list"), ("deps", "list"), ("deps", "tree"),
    ("profile", "list"), ("project", "list"), ("workspace", "list"), ("config", "list"), ("log",),
}
CACHE_ENTRIES = 400                 # これより多ければ、使っていないものから捨てる
CACHE_DAYS = 14                     # これより古いものは読み込まない


def _cacheable(args: list[str]) -> bool:
    command = tuple(a for a in args[:2] if not a.startswith("-"))
    return command in CACHEABLE and "--gui" not in args


class QueryCache:
    """読むだけのコマンドの結果を覚える（場所とコマンドごと）。GUIの設定の場所の cache.json に残し、起動し直しても使う。

    同じものを同時に読むときは、1回だけ実行して結果を分ける（画面が2つあっても）。"""

    def __init__(self, path: Path | None):
        self.path = path
        self.lock = threading.Lock()
        self.entries: dict[str, dict] = {}
        self.running: dict[str, threading.Event] = {}
        if path is not None and path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                limit = time.time() - CACHE_DAYS * 86400
                self.entries = {k: v for k, v in data.get("entries", {}).items() if v.get("time", 0) > limit}
            except (OSError, ValueError):
                self.entries = {}

    @staticmethod
    def key(directory: str | None, args: list[str]) -> str:
        return (_key(directory) if directory else "") + "\n" + "\0".join(args)

    def get(self, directory: str | None, args: list[str]) -> dict | None:
        with self.lock:
            entry = self.entries.get(self.key(directory, args))
            if entry is not None:
                entry["used"] = time.time()
            return dict(entry) if entry is not None else None

    def fetch(self, cli: "Cli", directory: str | None, args: list[str]) -> dict:
        """実行して覚える（失敗した結果は覚えない）。同じものを実行中なら、その結果を待つ。"""
        key = self.key(directory, args)
        with self.lock:
            waiting = self.running.get(key)
            if waiting is None:
                self.running[key] = threading.Event()
        if waiting is not None:
            waiting.wait(600)
            entry = self.get(directory, args)
            if entry is not None and not entry.get("stale"):
                return entry
            return {"doc": cli.run(directory, args), "time": time.time()}
        try:
            document = cli.run(directory, args)
            entry = {"doc": document, "time": time.time(), "used": time.time()}
            if document.get("ok"):
                with self.lock:
                    self.entries[key] = entry
                    self._trim()
                self._save()
            return entry
        finally:
            with self.lock:
                self.running.pop(key).set()

    def invalidate(self) -> None:
        """変える操作の後：覚えた結果をすべて「古い」にする（画面は出してから読み直す）。"""
        with self.lock:
            for entry in self.entries.values():
                entry["stale"] = True
        self._save()

    def _trim(self) -> None:
        if len(self.entries) > CACHE_ENTRIES:
            for key, _ in sorted(self.entries.items(), key=lambda item: item[1].get("used", 0))[:len(self.entries) - CACHE_ENTRIES]:
                del self.entries[key]

    def _save(self) -> None:
        if self.path is None:
            return
        with self.lock:
            text = json.dumps({"entries": self.entries}, ensure_ascii=False)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            pass


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

    def run(self, directory: str | None, args: list[str], stdin: str | None = None,
            progress: list[str] | None = None) -> dict:
        """progress：渡せば、実行中に標準エラーの行（ecobuild の経過）をここに足していく（画面が読みに来る）。"""
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
            if progress is None:
                completed = subprocess.run(argv, input=stdin or "", capture_output=True, encoding="utf-8",
                                           errors="replace", env=env, cwd=_working_directory(directory, args),
                                           **_no_window())
            else:
                completed = _run_streaming(argv, stdin or "", env, _working_directory(directory, args), progress)
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


def _run_streaming(argv: list[str], stdin: str, env: dict, cwd: str, lines: list[str]) -> subprocess.CompletedProcess:
    """subprocess.run と同じ結果を返す。標準エラーは読んだ行から lines に足す。"""
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               encoding="utf-8", errors="replace", env=env, cwd=cwd, **_no_window())
    errors: list[str] = []

    def read_errors() -> None:
        for line in process.stderr:
            errors.append(line)
            if line.strip():
                lines.append(line.strip())

    reader = threading.Thread(target=read_errors, daemon=True)
    reader.start()
    # communicate は標準エラーも読むので使わない（経過の行を取り合う）
    try:
        process.stdin.write(stdin)
        process.stdin.close()
    except OSError:          # 入力を読まずに終わった
        pass
    stdout = process.stdout.read()
    process.wait()
    reader.join()
    return subprocess.CompletedProcess(argv, process.returncode, stdout, "".join(errors))


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
    # pipx の置き場所も（インストーラーが PATH に足しても、サインインし直すまでショートカットから起動した GUI には届かないことがある）
    pipx_bin = Path(os.environ.get("PIPX_BIN_DIR") or Path.home() / ".local" / "bin")
    for scripts in (Path(sys.executable).parent, pipx_bin):
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

def _git(root: Path, *args: str, timeout: float = 60) -> str:
    """git を実行して標準出力を返す（失敗なら空）。stdin は空に（GUIのサーバーの stdin を引き継がない）。

    終わらなければ子ごと止めて GuiError（Windows の git は cmd/git.exe が本体を子で動かすので、片方だけ止めると
    出力のパイプが閉じずに待ち続ける）。"""
    process = subprocess.Popen(["git", "-C", str(root), *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, encoding="utf-8", errors="replace", **_no_window())
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        raise GuiError(f"git が{int(timeout)}秒たっても終わりません：git {' '.join(args)}") from None
    return stdout if process.returncode == 0 else ""


def _kill_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, stdin=subprocess.DEVNULL,
                       **_no_window())
    else:
        process.kill()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass


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
                               capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, **_no_window())
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
                               capture_output=True, encoding="mbcs", errors="replace", stdin=subprocess.DEVNULL, **_no_window())
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


def rename_folder(directory: str, source: str, destination: str) -> dict:
    """フォルダの名前を変える・移す（中身ごと）。Project のフォルダそのものは project move で（ビルドの設定も変わるため）。"""
    origin, target = _inside(directory, source), _inside(directory, destination)
    root = Path(directory).resolve()
    if origin == root or not origin.is_dir():
        raise GuiError(f"フォルダが見つかりません：{source}")
    if target.exists():
        raise GuiError(f"すでに存在します：{destination}")
    if origin in target.parents:
        raise GuiError("フォルダをその中へは移せません。")
    target.parent.mkdir(parents=True, exist_ok=True)
    origin.rename(target)
    return {"path": target.relative_to(root).as_posix()}


def remove_folder(directory: str, relative: str) -> dict:
    """フォルダを中身ごと削除する（作業空間の中だけ。作業空間そのもの・.git は消さない）。"""
    import shutil
    target = _inside(directory, relative)
    if target == Path(directory).resolve() or not target.is_dir():
        raise GuiError(f"フォルダが見つかりません：{relative}")
    shutil.rmtree(target)
    return {"path": relative}


IMPORT_LIMIT = 100 * 1024 * 1024    # 一度に取り込む大きさの上限（画面から送るので、大きなものは送らない）


def import_files(directory: str, target: str, files: list[dict]) -> dict:
    """エクスプローラーに落としたファイル・フォルダ（PCのほかの場所のもの）を、作業空間の target の下に置く。
    files：[{"path": target からの相対パス, "data": base64}]（フォルダは中のファイルを並べる。空のフォルダは "data" なし）。
    既にあるファイルは上書きしない（1つでもあれば、何も置かずに止める）。"""
    import base64
    base = _inside(directory, target) if target else Path(directory).resolve()
    if not base.is_dir():
        raise GuiError(f"フォルダが見つかりません：{target}")
    planned = []
    for item in files:
        relative = str(item.get("path") or "").replace("\\", "/").strip("/")
        if not relative:
            continue
        destination = _inside(directory, f"{target}/{relative}" if target else relative)
        planned.append((destination, item.get("data")))
    existing = [p.relative_to(Path(directory).resolve()).as_posix() for p, data in planned if data is not None and p.exists()]
    if existing:
        raise GuiError("同じ名前のファイルがあります（上書きしません）：" + "、".join(existing[:5]) + ("…" if len(existing) > 5 else ""))
    written = []
    for destination, data in planned:
        if data is None:
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(base64.b64decode(data))
        written.append(destination.relative_to(Path(directory).resolve()).as_posix())
    return {"files": written}


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
                               capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    return {"path": completed.stdout.strip()}


_me: dict = {}


def who_am_i() -> str:
    """ログイン中のGitHubのアカウント（画面で「自分」を示すため）。ecobuild にこれを返すコマンドはない。"""
    if "login" not in _me:
        try:
            completed = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, stdin=subprocess.DEVNULL,
                                       encoding="utf-8", errors="replace", timeout=20, **_no_window())
            _me["login"] = completed.stdout.strip() if completed.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            _me["login"] = ""
    return os.environ.get("ECOBUILD_GUI_ME") or _me["login"]


def github_account() -> dict:
    """ログイン中の GitHub のアカウント（アカウントの画面のため）：ログイン名・プロフィールの名前・URL と、gh のログインの権限。
    ecobuild にこれを返すコマンドはない。ログインし直した後のために、毎回 GitHub に聞く（「自分」も覚え直す）。"""
    try:
        completed = subprocess.run(["gh", "api", "-i", "user"], capture_output=True, stdin=subprocess.DEVNULL,
                                   encoding="utf-8", errors="replace", timeout=20, **_no_window())
    except (OSError, subprocess.TimeoutExpired):
        completed = None
    account = {"login": "", "name": "", "url": "", "scopes": []}
    if completed is not None and completed.returncode == 0:
        head, _, body = completed.stdout.replace("\r\n", "\n").partition("\n\n")
        for line in head.splitlines():
            key, _, value = line.partition(":")
            if key.strip().lower() == "x-oauth-scopes":
                account["scopes"] = sorted(s.strip() for s in value.split(",") if s.strip())
        try:
            user = json.loads(body)
        except ValueError:
            user = {}
        account.update(login=user.get("login") or "", name=user.get("name") or "", url=user.get("html_url") or "")
    _me["login"] = account["login"]
    account["login"] = who_am_i()
    return account


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


GH_SCOPES = {"delete_repo", "project", "workflow"}   # 画面から追加を頼める gh の権限


def refresh_scope(scope: str) -> None:
    """gh のログインに権限を足す（gh auth refresh。ブラウザで承認する）。対話が要るので、新しい端末の窓で動かす。"""
    if scope not in GH_SCOPES:
        raise GuiError(f"対応していない権限です：{scope}")
    if os.name != "nt":
        raise GuiError(f"ターミナルで gh auth refresh -h github.com -s {scope} を実行してください。")
    subprocess.Popen(["cmd", "/c", f"gh auth refresh -h github.com -s {scope} & pause"],
                     creationflags=subprocess.CREATE_NEW_CONSOLE)


def gh_login(switch: bool) -> None:
    """gh に別のアカウントでログインする（gh auth login。ブラウザで承認する）か、ログイン済みのアカウントに切り替える
    （gh auth switch）。対話が要るので、新しい端末の窓で動かす。"""
    command = "gh auth switch -h github.com" if switch else "gh auth login -h github.com -w -s project"
    if os.name != "nt":
        raise GuiError(f"ターミナルで {command} を実行してください。")
    subprocess.Popen(["cmd", "/c", f"{command} & pause"], creationflags=subprocess.CREATE_NEW_CONSOLE)


# HTTP --------------------------------------------------------------------------------------------

class Events:
    """開いている画面へ知らせること（実行したこと・画面の移動・知らせ）。画面は events で待ち受ける（長いポーリング）。"""

    def __init__(self, keep: int = 300):
        self.items: deque[dict] = deque(maxlen=keep)
        self.seq = 0
        self.changed = threading.Condition()

    def publish(self, event: dict) -> dict:
        with self.changed:
            self.seq += 1
            event = {**event, "seq": self.seq, "time": time.time()}
            self.items.append(event)
            self.changed.notify_all()
        return event

    def since(self, seq: int, wait: float) -> list[dict]:
        with self.changed:
            if not any(e["seq"] > seq for e in self.items):
                self.changed.wait(wait)
            return [e for e in self.items if e["seq"] > seq]


WINDOW_ALIVE = 50     # 秒。画面はこれより短い間隔で events を呼ぶ（呼ばなくなった窓は閉じたとみなす）


class App:
    def __init__(self, cli: Cli, store: Store, token: str, port: int):
        self.cli, self.store, self.token, self.port = cli, store, token, port
        self.last_contact = time.monotonic()
        self.server: ThreadingHTTPServer | None = None
        self.progress: dict[str, list[str]] = {}    # 実行中のコマンドの経過（画面が付けた番号 → 行）
        self.cache = QueryCache(None if store is None else store.path.with_name("cache.json"))
        self.events = Events()
        self.windows: dict[str, dict] = {}       # 開いている窓（画面が知らせる：種類・モジュール・画面・タブ・タスク）

    # GUIの操作（actions.py）。画面のボタンも、ecobuild gui・MCP も、ここを通る ------------------------------------
    def see_window(self, window: dict) -> None:
        key = str(window.get("id") or "")
        if key:
            self.windows[key] = {**self.windows.get(key, {}), **window, "seen": time.time()}

    def live_windows(self) -> list[dict]:
        now = time.time()
        return [w for w in self.windows.values() if now - w.get("seen", 0) < WINDOW_ALIVE]

    def module_window(self, root: str) -> dict | None:
        return next((w for w in self.live_windows() if w.get("kind") == "module" and w.get("module")
                     and _same(w["module"], root)), None)

    def action(self, name: str, params: dict, origin: str = "", progress=None) -> object:
        try:
            p = gui_actions.check(name, params)
        except ValueError as error:
            raise GuiError(str(error)) from None
        by = "window" if origin and origin in self.windows else "agent"
        if name == "run":
            body = {"dir": p.get("dir"), "args": p["args"], "stdin": p.get("stdin"), "progress": progress}
            document = self.api("cli", body)
            if not _read_only(p["args"]) and not _cacheable(p["args"]):
                error = document.get("error") or {}
                self.events.publish({"type": "ran", "by": by, "origin": origin, "dir": p.get("dir"),
                                     "args": p["args"], "ok": bool(document.get("ok")),
                                     "message": error.get("message") if error else None})
            return document
        if name == "open":
            return self._open(p, origin, by)
        if name == "folder":
            if origin in self.windows:
                return {"apply": {"open": {"dir": p["dir"], "path": p.get("path", ""), "reveal": p.get("reveal", False)}}}
            target = self.module_window(p["dir"]) or next(iter(self.live_windows()), None)
            if target:
                self.events.publish({"type": "open-path", "target": target["id"], "by": by, "dir": p["dir"],
                                     "path": p.get("path", ""), "reveal": p.get("reveal", False)})
                return {"done": "asked", "window": target["id"]}
            return open_path(p["dir"], p.get("path", ""), p.get("reveal", False))
        if name == "vs":
            if p.get("path"):
                return open_file_in_visual_studio(p["dir"], p["path"], p.get("version", "2026"))
            return open_in_visual_studio(p["dir"], p.get("version", "2026"))
        if name == "notify":
            self.events.publish({"type": "notify", "by": by, "message": p["message"], "kind": p.get("kind", "info")})
            return {"windows": len(self.live_windows())}
        if name == "windows":
            now = time.time()
            return [{k: v for k, v in {**w, "seen_seconds_ago": round(now - w["seen"])}.items() if k != "seen"}
                    for w in self.live_windows()]
        if name == "activity":
            count = p.get("count", 30)
            return [e for e in self.events.items if e["type"] in ("ran", "notify", "navigate", "open-window")][-count:]
        raise GuiError(f"GUIの操作 {name} はまだ使えません。")

    def _open(self, p: dict, origin: str, by: str) -> dict:
        """open：module を省けばハブ。開いている窓があれば移り、なければ開く（呼んだのが窓なら、その窓が行う）。"""
        where = {k: p[k] for k in ("page", "tab", "task", "command") if k in p}
        module = p.get("module")
        if not module:
            page = "hub.html" + ("#help" + ("/commands/" + urllib.parse.quote(p["command"]) if p.get("command") else "")
                                 if p.get("page") == "help" or p.get("command") else "")
            here = self.windows.get(origin)
            target = here if here and here.get("kind") == "hub" else                 next((w for w in self.live_windows() if w.get("kind") == "hub"), None)
        else:
            root = self._module_path(module)
            page = "module.html?path=" + urllib.parse.quote(root) + _hash(where)
            here = self.windows.get(origin)
            target = here if here and here.get("kind") == "module" and here.get("module") and _same(here["module"], root)                 else self.module_window(root)
        if target:
            event = {"type": "navigate", "target": target["id"], "by": by, **where}
            if target["id"] == origin:
                return {"apply": {"navigate": where}}
            self.events.publish(event)
            return {"done": "navigated", "window": target["id"]}
        if origin in self.windows:
            return {"apply": {"open-window": page}}
        opener = next(iter(self.live_windows()), None)
        if opener:      # Electron の窓は、開いている窓が開く（サーバーは Electron の窓を開けない）
            self.events.publish({"type": "open-window", "target": opener["id"], "by": by, "page": page})
            return {"done": "asked", "window": opener["id"]}
        base, _, fragment = page.partition("#")
        open_window(f"http://127.0.0.1:{self.port}/{base}{'&' if '?' in base else '?'}t={self.token}"
                    + (f"#{fragment}" if fragment else ""))
        return {"done": "opened"}

    def _module_path(self, module: str) -> str:
        """モジュールのフォルダか名前から、このPCの作業空間のフォルダ。"""
        if Path(module).expanduser().is_dir():
            return str(_module_root(Path(module)))
        listed = self.cli.run(None, ["workspace", "list"])
        for entry in listed.get("result") or []:
            path = entry.get("path", "")
            if entry.get("exists") and (Path(path).name.casefold() == module.casefold()
                                        or (entry.get("repository") or "").casefold() in (module.casefold(),)
                                        or (entry.get("repository") or "").split("/")[-1].casefold() == module.casefold()):
                return path
        raise GuiError(f"モジュール {module} がこのPCに見つかりません（ecobuild workspace list）。")

    def move_legacy(self) -> None:
        """以前の gui.json に登録したフォルダを、ecobuild の作業空間の記録（workspace add）へ移す（一度だけ）。"""
        modules, workspaces = self.store.take_legacy()
        for path in modules + workspaces:
            if (Path(path) / MODULE_FILE).is_file():
                self.cli.run(None, ["workspace", "add", path])

    def api(self, name: str, body: dict) -> object:
        d = body.get
        if name == "cli":
            args = list(d("args") or [])
            if not _cacheable(args) and not _read_only(args):
                self.cache.invalidate()        # 変える操作：覚えた結果は古い（実行中に読み直したものも古いことがあるので、後でもう一度）
            key = str(d("progress") or "")
            try:
                if not key:
                    return self.cli.run(d("dir") or None, args, d("stdin"))
                lines = self.progress.setdefault(key, [])
                try:
                    return self.cli.run(d("dir") or None, args, d("stdin"), progress=lines)
                finally:
                    self.progress.pop(key, None)
            finally:
                if not _cacheable(args) and not _read_only(args):
                    self.cache.invalidate()
        if name == "action":
            if d("window"):
                self.see_window(dict(d("window")))   # 呼んだ窓（まだ待ち受けを始めていなくても、その窓だと分かるように）
            return self.action(str(d("name") or ""), dict(d("params") or {}), str(d("origin") or ""), d("progress"))
        if name == "events":
            # 画面の待ち受け：window（その窓の今の状態）を覚え、since より新しい知らせを返す（なければ少し待つ）
            if d("window"):
                self.see_window(dict(d("window")))
            since = d("since")
            if since is None:
                return {"seq": self.events.seq, "events": []}
            items = self.events.since(int(since), float(d("wait") or 20))
            return {"seq": self.events.seq, "events": items}
        if name == "window-state":
            self.see_window(dict(d("window") or {}))
            return {}
        if name == "query":
            # 覚える読むだけのコマンド。mode "cache"：覚えた結果だけ（なければ None）。"fresh"：実行して覚える。
            # 答え：{"doc": 結果, "time": 実行した時刻（秒）, "stale": 変える操作の後なら true}
            args = list(d("args") or [])
            if not _cacheable(args):
                raise GuiError("覚えておけないコマンドです：" + " ".join(args))
            if d("mode") == "cache":
                return self.cache.get(d("dir") or None, args)
            return self.cache.fetch(self.cli, d("dir") or None, args)
        if name == "prefetch":
            # 最初の結果をまとめて読んで覚える（モジュールを作った・取得したとき。ひらく前に用意しておく）
            from concurrent.futures import ThreadPoolExecutor
            queries = [list(q) for q in d("queries") or [] if _cacheable(list(q))]
            with ThreadPoolExecutor(max_workers=4) as pool:
                done = list(pool.map(lambda q: self.cache.fetch(self.cli, d("dir") or None, q)["doc"].get("ok", False), queries))
            return {"read": sum(done), "of": len(queries)}
        if name == "progress":
            return {"lines": list(self.progress.get(str(d("id") or ""), []))}
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
        if name == "remove-folder":
            return remove_folder(d("dir"), d("path"))
        if name == "rename-folder":
            return rename_folder(d("dir"), d("source"), d("destination"))
        if name == "import-files":
            return import_files(d("dir"), d("target") or "", list(d("files") or []))
        if name == "mkparent":
            return make_parent(d("path"))
        if name == "shortcut":
            return {"made": make_shortcuts()}
        if name == "relaunch-after":
            return relaunch_after(int(d("pid") or 0))
        if name == "module-repository":
            return {"repository": module_repository(d("dir"))}
        if name == "account":
            return github_account()
        if name == "gh-login":
            gh_login(bool(d("switch")))
            return {}
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


def _hash(where: dict) -> str:
    """モジュールの窓の URL の # の部分（#modinfo/projects・#tasks/12・#help/commands/task%20start）。"""
    page = where.get("page") or ("modinfo" if where.get("tab") else "tasks" if where.get("task") else
                                 "help" if where.get("command") else "")
    if not page:
        return ""
    extra = where.get("tab") if page == "modinfo" else str(where.get("task")) if page == "tasks" and where.get("task") else \
        "commands/" + urllib.parse.quote(where["command"]) if page == "help" and where.get("command") else ""
    return "#" + page + ("/" + extra if extra else "")


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
                               capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, **_no_window())
    return [Path(line) for line in completed.stdout.splitlines() if line.strip()]


# タスクバーでの「同じアプリ」の印（electron/main.js の app.setAppUserModelId と同じ）。ショートカットにも付けると、
# ピン留めしたボタンと開いている窓が1つのボタンにまとまり、開いている窓をピン留めしてもこのショートカットになる。
APP_ID = "ECOBuild.GUI"

# ショートカット（.lnk）に AppUserModelID（System.AppUserModel.ID）を書く。PowerShell の Add-Type で使う。
_SET_APP_ID = r"""
using System;
using System.Runtime.InteropServices;
public static class EcoShortcut {
    [StructLayout(LayoutKind.Sequential)] struct PropertyKey { public Guid fmtid; public uint pid; }
    [StructLayout(LayoutKind.Sequential)] struct PropVariant { public ushort vt; ushort r1, r2, r3; public IntPtr value; IntPtr extra; }
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore {
        void GetCount(out uint count);
        void GetAt(uint index, out PropertyKey key);
        void GetValue(ref PropertyKey key, out PropVariant value);
        void SetValue(ref PropertyKey key, ref PropVariant value);
        void Commit();
    }
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHGetPropertyStoreFromParsingName(string path, IntPtr bind, int flags, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out IPropertyStore store);
    public static void SetAppId(string link, string id) {
        Guid iid = typeof(IPropertyStore).GUID;
        IPropertyStore store;
        SHGetPropertyStoreFromParsingName(link, IntPtr.Zero, 2 /* GPS_READWRITE */, ref iid, out store);
        PropertyKey key = new PropertyKey { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };
        PropVariant value = new PropVariant { vt = 31 /* VT_LPWSTR */, value = Marshal.StringToCoTaskMemUni(id) };
        try { store.SetValue(ref key, ref value); store.Commit(); }
        finally { Marshal.FreeCoTaskMem(value.value); Marshal.ReleaseComObject(store); }
    }
}
"""


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
        # そのあと AppUserModelID を付ける（WScript.Shell では付けられない）。
        script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:EG_LINK); $s.TargetPath = $env:EG_TARGET; "
                  "if ($env:EG_SCRIPT) { $s.Arguments = '\"' + $env:EG_SCRIPT + '\"' } else { $s.Arguments = '' }; $s.WorkingDirectory = $env:EG_DIR; "
                  "$s.IconLocation = $env:EG_ICON + ',0'; $s.Description = 'ECOBuild GUI'; $s.Save(); "
                  "Add-Type -TypeDefinition $env:EG_CS; [EcoShortcut]::SetAppId($env:EG_LINK, $env:EG_APPID)")
        # インストールしたアプリなら、その exe を開く（引数なし）
        target, opens = (str(packaged_app()), "") if packaged_app() else (_pythonw(), str(here / "ECOBuildGUI.pyw"))
        env = dict(os.environ, EG_LINK=str(link), EG_TARGET=target, EG_SCRIPT=opens,
                   EG_DIR=str(here), EG_ICON=str(here / "icon.ico"), EG_CS=_SET_APP_ID, EG_APPID=APP_ID)
        completed = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env, stdin=subprocess.DEVNULL,
                                   capture_output=True, encoding="utf-8", errors="replace", **_no_window())
        if completed.returncode != 0 or not link.is_file():
            raise GuiError(f"ショートカットを作成できませんでした：{link}\n{completed.stderr.strip()}")
        made.append(str(link))
    return made


def relaunch_after(pid: int) -> dict:
    """pid のプロセス（ECOBuild を更新している窓）が終わったら GUI を起動し直す、切り離したプロセスを始める。
    GUI はこの後に終了する（更新で置き換えられるように）。pid が 0 なら待たない。"""
    _start_detached([_pythonw(), str(Path(__file__).resolve()), "--relaunch-after", str(pid)], no_window=True)
    return {}


def _wait_and_relaunch(pid: int) -> None:
    """--relaunch-after：pid が終わるのを待ち（最長2時間）、古い GUI が終わる間をおいて、新しいプロセスで GUI を開く
    （更新で入れ替わったファイルを読むように。ショートカットと同じ起動のしかた）。"""
    if pid and os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x00100000, False, pid)   # SYNCHRONIZE
        if handle:
            kernel32.WaitForSingleObject(handle, 2 * 60 * 60 * 1000)
            kernel32.CloseHandle(handle)
    elif pid:
        deadline = time.monotonic() + 2 * 60 * 60
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                break
            time.sleep(1)
    time.sleep(2)
    here = Path(__file__).resolve().parent
    _start_detached([str(packaged_app())] if packaged_app() else [_pythonw(), str(here / "ECOBuildGUI.pyw")], no_window=True)


def _pythonw() -> str:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate) if os.name == "nt" and candidate.is_file() else sys.executable


ELECTRON_APP = Path(__file__).resolve().with_name("electron")


def packaged_app() -> Path | None:
    """インストーラー（Setup.exe）で入れた GUI なら、そのアプリの exe。この GUI は <入れた場所>/resources/gui にある。"""
    candidate = Path(__file__).resolve().parent.parent.parent / "ECOBuild GUI.exe"
    return candidate if os.name == "nt" and Path(__file__).resolve().parent.parent.name == "resources" and candidate.is_file() else None


def _electron() -> Path | None:
    """インストールしたアプリ、または electron/ に入れた Electron（cd gui/electron; npm install）。なければ None。"""
    if packaged_app():
        return packaged_app()
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
    _start_detached([str(electron)] if packaged_app() else [str(electron), str(ELECTRON_APP)], env=env)
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


def install_command(ecobuild: list[str]) -> Path | None:
    """ecobuild-gui コマンドを、ecobuild と同じフォルダに置く（ecobuild gui … で呼べる：ecobuild の外部サブコマンド）。
    中身は、このGUIの ecobuild_gui.py を呼ぶだけ。書けなければ何もしない。"""
    script = Path(__file__).with_name("ecobuild_gui.py").resolve()
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe" and python.with_name("python.exe").is_file():
        python = python.with_name("python.exe")      # 端末に出力するので、窓のない pythonw ではなく python
    # ecobuild のある所（PATH の上）。リンク（pipx 等）はたどらない：たどった先は PATH にないことがある
    folder = Path(os.path.abspath(ecobuild[0])).parent if ecobuild and Path(ecobuild[0]).exists() else None
    if folder is None:
        return None
    if os.name == "nt":
        target, text = folder / "ecobuild-gui.cmd", f'@"{python}" "{script}" %*\r\n'
    else:
        target, text = folder / "ecobuild-gui", f'#!/bin/sh\nexec "{python}" "{script}" "$@"\n'
    try:
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8", newline="")
            if os.name != "nt":
                target.chmod(0o755)
        return target
    except OSError:
        return None


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
    # どの動き方でも、動いているサーバーの場所を残す（ecobuild gui がここに頼む）
    _state_file().parent.mkdir(parents=True, exist_ok=True)
    _state_file().write_text(json.dumps({**state, "mode": "serve" if args.serve else "electron" if args.electron else "foreground"}),
                             encoding="utf-8")
    install_command(cli.command)
    if args.serve:
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
        if (_read_state() or {}).get("pid") == os.getpid():
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
    parser.add_argument("--relaunch-after", type=int, default=None, help=argparse.SUPPRESS)  # 更新の後に起動し直す（relaunch_after）
    args = parser.parse_args(argv)
    if args.relaunch_after is not None:
        _wait_and_relaunch(args.relaunch_after)
    elif args.shortcut:
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
