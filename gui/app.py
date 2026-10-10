"""ECOBuildのGUI：画面（static/）を配り、画面からの依頼で ecobuild のCLIを実行する。

ECOBuildの実装（src/ のパッケージ）とは独立している。ECOBuildのコードは読み込まず、ecobuild コマンドを呼ぶだけ。
使うのは Python の標準ライブラリだけ（3.11 以上）。起動：python gui/app.py（または ECOBuildGUI.pyw をダブルクリック）

- 起動すると、窓のない Python（pythonw）でサーバーを裏で動かし、GUIの窓を開いて、起動したコマンドはすぐ終わる。
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
import json
import mimetypes
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


STALE_MESSAGE = ("GUIが更新されています。GUIをもう一度起動すると、新しいものに入れ替わります（この窓は閉じてください）。")
IDLE_SECONDS = int(os.environ.get("ECOBUILD_GUI_IDLE") or 180)  # 画面から連絡がこの秒数なければ、裏で動くサーバーは終わる（画面は20秒ごとに連絡する）
STATIC = Path(__file__).with_name("static")
DEFAULT_PORT = 8765
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}

# 何も変えないコマンド（同じ場所で他のコマンドが動いていても待たずに実行する）。
READ_ONLY = {
    ("status",), ("log",), ("show",), ("diff",), ("blame",), ("types",), ("doctor",), ("config", "list"),
    ("config", "get"), ("task", "list"), ("task", "status"), ("task", "workload"), ("task", "next"),
    ("task", "overdue"), ("pr", "list"), ("pr", "status"), ("pr", "diff"), ("branch", "list"), ("deps", "list"),
    ("project", "list"), ("profile", "list"), ("milestone", "list"),
    ("milestone", "status"), ("sprint", "list"), ("sprint", "status"), ("stash", "list"), ("ci", "status"),
    ("release", "list"),
}


def _no_window() -> dict:
    """Windowsで子プロセスの黒い窓を出さない。"""
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


class Store:
    """GUIだけが使う記録（モジュールの一覧・専用のcloneの場所）。ファイルは gui.json。"""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data.setdefault("modules", [])
        data.setdefault("workspaces", {})
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def modules(self) -> list[dict]:
        with self._lock:
            data = self._load()
        return [dict(item, exists=(Path(item["path"]) / "ecobuild.toml").is_file()) for item in data["modules"]]

    def add_module(self, path: str) -> dict:
        root = _module_root(Path(path))
        with self._lock:
            data = self._load()
            if not any(_same(item["path"], root) for item in data["modules"]):
                data["modules"].append({"path": root.as_posix(), "name": root.name})
                self._save(data)
        return {"path": root.as_posix(), "name": root.name}

    def order_modules(self, paths: list[str]) -> None:
        """一覧の並び（ハブでドラッグして並べ替えたもの）。知らない場所は無視し、指定のないものは後ろに残す。"""
        with self._lock:
            data = self._load()
            rank = {_key(p): i for i, p in enumerate(paths)}
            data["modules"].sort(key=lambda item: rank.get(_key(item["path"]), len(rank)))
            self._save(data)

    def remove_module(self, path: str) -> None:
        with self._lock:
            data = self._load()
            data["modules"] = [item for item in data["modules"] if not _same(item["path"], Path(path))]
            data["workspaces"].pop(_key(path), None)
            self._save(data)

    def workspaces(self, module: str) -> list[str]:
        """モジュールの専用のclone（task start --dir で作ったもの等）。消えた場所は除く。"""
        with self._lock:
            data = self._load()
        return [d for d in data["workspaces"].get(_key(module), []) if (Path(d) / ".git").exists()]

    def add_workspace(self, module: str, directory: str) -> list[str]:
        root = _module_root(Path(directory))
        with self._lock:
            data = self._load()
            items = data["workspaces"].setdefault(_key(module), [])
            if not _same(module, root) and not any(_same(d, root) for d in items):
                items.append(root.as_posix())
                self._save(data)
        return self.workspaces(module)

    def remove_workspace(self, module: str, directory: str) -> list[str]:
        with self._lock:
            data = self._load()
            items = data["workspaces"].get(_key(module), [])
            data["workspaces"][_key(module)] = [d for d in items if not _same(d, Path(directory))]
            self._save(data)
        return self.workspaces(module)


def _key(path: str | Path) -> str:
    return Path(path).resolve().as_posix().lower()


def _same(a: str | Path, b: str | Path) -> bool:
    return _key(a) == _key(b)


def _module_root(path: Path) -> Path:
    """ecobuild.toml のある場所（指定した場所か、その上）。"""
    path = path.expanduser().resolve()
    for candidate in (path, *path.parents):
        if (candidate / "ecobuild.toml").is_file():
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
            raise GuiError(f"場所がありません：{directory}")
        argv = list(self.command) + (["-C", directory] if directory else []) + args + ["--json"]
        read_only = tuple(a for a in args[:2] if not a.startswith("-")) in READ_ONLY or (args[0],) in READ_ONLY
        lock = None if read_only else self._lock_for(directory)
        if lock:
            lock.acquire()
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", GIT_TERMINAL_PROMPT="0")
            completed = subprocess.run(argv, input=stdin or "", capture_output=True, encoding="utf-8",
                                       errors="replace", env=env, cwd=directory or str(Path.home()),
                                       **_no_window())
        finally:
            if lock:
                lock.release()
        document = _last_json(completed.stdout)
        if document is None:
            document = {"ok": False, "command": " ".join(args), "result": None, "notices": [],
                        "error": {"code": "gui_no_output",
                                  "message": "ecobuild の結果を読めませんでした。",
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
        raise GuiError(f"場所がありません：{root}")
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
    return {"root": root.as_posix(), "files": files, "dirs": sorted(dirs), "missing": missing}


def _inside(directory: str, relative: str) -> Path:
    root = Path(directory).resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise GuiError("場所の外は指定できません。")
    if ".git" in target.relative_to(root).parts:
        raise GuiError(".git の中は扱えません。")
    return target


def make_directory(directory: str, relative: str) -> dict:
    target = _inside(directory, relative)
    if target.exists():
        raise GuiError(f"既にあります：{relative}")
    target.mkdir(parents=True)
    return {"path": target.relative_to(Path(directory).resolve()).as_posix()}


def module_defaults(directory: str) -> dict:
    """画面に既定値を入れておくための、モジュールの設定の一部（ecobuild.toml）。ecobuild にこれを返すコマンドがないため、
    GUIが読む。読めなければ空（画面は既定値を入れないだけ）。"""
    import tomllib
    try:
        data = tomllib.loads((_module_root(Path(directory)) / "ecobuild.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError, GuiError):
        return {}
    branches = data.get("branches") if isinstance(data.get("branches"), dict) else {}
    base = branches.get("default_base")
    return {"default_base": base} if isinstance(base, str) and base else {}


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
        raise GuiError(f"知らない Visual Studio の版です：{version}")
    solution = find_solution(directory)
    if solution is None:
        return {"solution": None}
    devenv = _visual_studio(version)
    if not devenv:
        others = [v for v in visual_studio_versions() if v != version]
        raise GuiError(f"Visual Studio {version} が見つかりません。"
                       + (f"このPCにあるのは {'・'.join(others)} です。ボタンの横で切り替えてください。" if others else ""))
    subprocess.Popen([devenv, str(solution)], cwd=str(solution.parent))
    return {"solution": solution.as_posix(), "devenv": devenv, "version": version}


def make_file(directory: str, relative: str) -> dict:
    """空のファイルを作る（型が ecobuild file add に対応しないとき：generic 等）。"""
    target = _inside(directory, relative)
    if target.exists():
        raise GuiError(f"既にあります：{relative}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    return {"path": target.relative_to(Path(directory).resolve()).as_posix()}


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
        raise GuiError(f"ありません：{relative}")
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
        raise GuiError(f"ファイルがありません：{relative}")
    data = target.read_bytes()[:400_000]
    if b"\0" in data[:8000]:
        return {"binary": True, "text": ""}
    return {"binary": False, "text": data.decode("utf-8", errors="replace"), "truncated": target.stat().st_size > len(data)}


_PICK = r"""
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
path = filedialog.askdirectory(title=sys.argv[1], initialdir=sys.argv[2] or None, mustexist=False)
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


# HTTP --------------------------------------------------------------------------------------------

class App:
    def __init__(self, cli: Cli, store: Store, token: str, port: int):
        self.cli, self.store, self.token, self.port = cli, store, token, port
        self.last_contact = time.monotonic()
        self.server: ThreadingHTTPServer | None = None

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
        if name == "modules":
            return self.store.modules()
        if name == "modules/add":
            return self.store.add_module(d("path"))
        if name == "modules/order":
            self.store.order_modules(list(d("paths") or []))
            return {}
        if name == "modules/remove":
            self.store.remove_module(d("path"))
            return {}
        if name == "workspaces":
            return self.store.workspaces(d("module"))
        if name == "workspaces/add":
            return self.store.add_workspace(d("module"), d("dir"))
        if name == "workspaces/remove":
            return self.store.remove_workspace(d("module"), d("dir"))
        if name == "files":
            return list_files(d("dir"))
        if name == "mkdir":
            return make_directory(d("dir"), d("path"))
        if name == "module-defaults":
            return module_defaults(d("dir"))
        if name == "open-vs":
            return open_in_visual_studio(d("dir"), d("version") or "2026")
        if name == "vs-versions":
            return visual_studio_versions()
        if name == "touch":
            return make_file(d("dir"), d("path"))
        if name == "mkparent":
            return make_parent(d("path"))
        if name == "shortcut":
            return {"made": make_shortcuts()}
        if name == "open-window":
            # GUIの別の画面（モジュールの窓）を、ハブと同じアプリの窓で開く（画面の window.open では普通のタブになるため）。
            page = d("page") or ""
            if not page.startswith(("module.html?", "hub.html")) or "//" in page or "\\" in page.split("?")[0]:
                raise GuiError("開けない画面です。")
            separator = "&" if "?" in page else "?"
            open_window(f"http://127.0.0.1:{self.port}/{page}{separator}t={self.token}")
            return {}
        if name == "open":
            return open_path(d("dir"), d("path") or "", bool(d("reveal")))
        if name == "read":
            return read_text(d("dir"), d("path"))
        if name == "pick-folder":
            return pick_folder(d("title") or "", d("initial") or "")
        raise GuiError(f"知らない操作です：{name}" + (f"。{STALE_MESSAGE}" if server_is_stale() else
                                                    "。GUIのサーバーが画面より古い可能性があります。起動し直してください。"))


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
                return self._json(HTTPStatus.FORBIDDEN, {"error": "合言葉が違います。GUIを開き直してください。"})
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


def open_window(url: str) -> None:
    """Edgeがあればアプリの窓（アドレスバーなし）で、なければ既定のブラウザで開く。"""
    edge = _edge() if os.name == "nt" else None
    if edge:
        subprocess.Popen([edge, f"--app={url}"])
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
        raise GuiError("ショートカットを作れるのは Windows だけです。")
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
            raise GuiError(f"ショートカットを作れませんでした：{link}\n{completed.stderr.strip()}")
        made.append(str(link))
    return made


def _pythonw() -> str:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate) if os.name == "nt" and candidate.is_file() else sys.executable


def launch(args) -> None:
    """裏でサーバーを動かして窓を開き、すぐ終わる。動いているサーバーがあれば使う（古ければ入れ替える）。"""
    state = _read_state()
    alive = _ping(state)
    if alive and not alive.get("stale"):
        if not args.no_browser:
            open_window(_url(state))
        _say(f"ECOBuild GUI を開きました（動いているサーバーを使います）：{_url(state)}")
        return
    if alive:   # 更新前のサーバー：止めてから新しく起動する
        _shutdown(state)
        time.sleep(1)
    # Find ecobuild here (with this terminal's PATH) so a missing one is reported now, and the server uses the same one.
    try:
        found = default_cli(args.ecobuild)
    except SystemExit as error:
        _alert(str(error))
        sys.exit(1)
    command = [_pythonw(), str(Path(__file__).resolve()), "--serve", "--port", str(args.port)]
    if len(found) == 1 and not os.environ.get("ECOBUILD_GUI_CLI"):
        command += ["--ecobuild", found[0]]
    if args.no_browser:
        command.append("--no-browser")
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200 | subprocess.CREATE_NO_WINDOW   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(command, creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        process = subprocess.Popen(command, start_new_session=True, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        state = _read_state()
        if state and state.get("pid") == process.pid and _ping(state):
            _say(f"ECOBuild GUI を起動しました：{_url(state)}\n（裏で動いています。GUIの窓をすべて閉じると、しばらくして終わります）")
            return
        if process.poll() is not None:
            break
        time.sleep(0.2)
    _alert(f"ECOBuild GUI を起動できませんでした。記録：{gui_home() / 'gui.log'}")
    sys.exit(1)


def serve(args) -> None:
    """サーバー本体。--serve（裏で動く）では、画面から連絡がなくなったら終わる。"""
    background = args.serve
    if background:
        # 窓がないので、エラーは記録に書く。
        gui_home().mkdir(parents=True, exist_ok=True)
        log = open(gui_home() / "gui.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
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
    server.RequestHandlerClass = make_handler(app)
    state = {"pid": os.getpid(), "port": port, "token": token}
    url = _url(state)
    if background:
        _state_file().parent.mkdir(parents=True, exist_ok=True)
        _state_file().write_text(json.dumps(state), encoding="utf-8")
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 起動：{url}（ecobuild：{' '.join(cli.command)}）")

        def watch():
            while True:
                time.sleep(15)
                if time.monotonic() - app.last_contact > IDLE_SECONDS:
                    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 画面がないので終わります")
                    server.shutdown()
                    return
        threading.Thread(target=watch, daemon=True).start()
    else:
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(errors="replace")
        print(f"ECOBuild GUI：{url}")
        print(f"ecobuild：{' '.join(cli.command)}")
        print("終了するには Ctrl+C を押してください。", flush=True)
    if cli_warning(cli.command):
        print("注意：" + cli_warning(cli.command))
    if not args.no_browser:
        open_window(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if background and (_read_state() or {}).get("pid") == os.getpid():
            try:
                _state_file().unlink()
            except OSError:
                pass


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ecobuild-gui", description="ECOBuildのGUIを開きます。")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"待ち受けるポート（既定 {DEFAULT_PORT}。"
                                                                       "使われていれば空いているもの）")
    parser.add_argument("--no-browser", action="store_true", help="窓を開かない（URLを表示するだけ）")
    parser.add_argument("--ecobuild", default="", help="ecobuild コマンドの場所（既定：PATH、なければ起動したPythonの環境）")
    parser.add_argument("--foreground", action="store_true", help="裏で動かさず、この端末でサーバーを動かす（Ctrl+C で終了。開発用）")
    parser.add_argument("--shortcut", action="store_true",
                        help="デスクトップとスタートメニューにショートカット（アイコン付き）を作って終わる")
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)   # 裏で動くサーバー（launch が使う）
    args = parser.parse_args(argv)
    if args.shortcut:
        try:
            _say("作りました：\n" + "\n".join(make_shortcuts()))
        except GuiError as error:
            _alert(str(error))
            sys.exit(1)
    elif args.serve or args.foreground:
        serve(args)
    else:
        launch(args)


if __name__ == "__main__":
    main()
