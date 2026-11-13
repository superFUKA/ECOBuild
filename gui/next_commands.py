"""ecobuild gui の、新しい GUI（gui/eco_gui）の画面が呼ぶ「この PC の窓まわり」のコマンド。ECOBuild のコマンドにはないもの：

  ecobuild gui login [--switch]                 GitHub にログインする（新しい端末の窓で gh auth login。--switch：gh auth switch）
  ecobuild gui scope <権限>                     gh のログインに権限を足す（新しい端末の窓で gh auth refresh -s <権限>）
  ecobuild gui pick-folder [--title …] [--initial …]   フォルダを選ぶ窓（OS の標準）。選んだ場所（選ばなければ空）
  ecobuild gui shortcut [--module <場所>] [--pick]     ショートカットを作る（--module：そのモジュールの窓を開くもの。
                                                --pick：置くフォルダを選ぶ窓を出す。省くとデスクトップ。--module なし：
                                                この GUI のもの。デスクトップとスタートメニュー）
  ecobuild gui quit                             新しい GUI を終える（窓をすべて閉じ、中継地点を止める）
  ecobuild gui update [--ref <版>]              ECOBuild を入れ直し（ecobuild installer update）、終わったら新しい GUI を起動し直す

画面は、ほかの ecobuild のコマンドと同じ形（COMMANDS）でこれを知り、同じ道（ecobuild gui …）で呼ぶ。
使うのは Python の標準ライブラリだけ（表示の CLI は next_gui の display で呼ぶ）。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from operator_kit import Failure

HERE = Path(__file__).resolve().parent
SCOPES = ("delete_repo", "project", "workflow")   # 画面から足せる gh の権限


def _str(param: str, help: str, required: bool = False) -> dict:
    return {"param": param, "type": "str", "required": required, "multiple": False, "help": help}


def _option(param: str, help: str, kind: str = "str") -> dict:
    return {"param": param, "names": ["--" + param.replace("_", "-")], "type": kind, "help": help}


# ecobuild --help --json のコマンドと同じ形（ecobuild_gui.COMMANDS に足す）
COMMANDS = [
    {"name": "login", "path": "gui login", "runnable": True, "effect": "change",
     "summary": "GitHub にログインします（新しい端末の窓で gh auth login。ブラウザーで承認します）。",
     "arguments": [], "options": [_option("switch", "ログイン済みのアカウントに切り替える（gh auth switch）", "bool")]},
    {"name": "scope", "path": "gui scope", "runnable": True, "effect": "change",
     "summary": "gh のログインに権限を足します（新しい端末の窓で gh auth refresh。ブラウザーで承認します）。",
     "arguments": [_str("scope", f"足す権限（{'・'.join(SCOPES)}）", required=True)], "options": []},
    {"name": "pick-folder", "path": "gui pick-folder", "runnable": True, "effect": "read",
     "summary": "フォルダを選ぶ窓（OS の標準）を出し、選んだ場所を答えます（選ばなければ空）。",
     "arguments": [], "options": [_option("title", "窓の題"), _option("initial", "最初に開いておく場所")]},
    {"name": "shortcut", "path": "gui shortcut", "runnable": True, "effect": "change",
     "summary": "ECOBuild GUI のショートカットを作ります（--module：そのモジュールの窓を開くもの。タスクバーでは、モジュールごとのアプリ）。",
     "arguments": [], "options": [_option("module", "モジュールのフォルダ（省くと、この GUI のショートカットをデスクトップとスタートメニューに）"),
                                  _option("place", "置くフォルダ（省くとデスクトップ）"),
                                  _option("pick", "置くフォルダを選ぶ窓を出す（前に選んだ場所から）", "bool")]},
    {"name": "quit", "path": "gui quit", "runnable": True, "effect": "human",
     "summary": "ECOBuild GUI を終了します（開いている窓をすべて閉じます。実行中のコマンドがあれば、終わってから）。",
     "arguments": [], "options": []},
    {"name": "update", "path": "gui update", "runnable": True, "effect": "human",
     "summary": "ECOBuild を入れ直し（ecobuild installer update）、終わったら ECOBuild GUI を起動し直します"
                "（別の窓のインストーラーが入れ直します。GUI はいったんすべての窓を閉じます）。",
     "arguments": [], "options": [_option("ref", "入れる版（ブランチ・タグ・コミット。省くと最新）")]},
]
NAMES = tuple(command["name"] for command in COMMANDS)


def parse(name: str, words: list[str]) -> dict:
    """--名前 値・--旗・「--」の後ろの位置引数を、COMMANDS の形に合わせて読む。"""
    spec = next(command for command in COMMANDS if command["name"] == name)
    options = {"--" + o["param"].replace("_", "-"): o for o in spec["options"]}
    values: dict = {}
    positional: list[str] = []
    i = 0
    while i < len(words):
        word = words[i]
        if word == "--":
            positional += words[i + 1:]
            break
        if word in options:
            option = options[word]
            if option["type"] == "bool":
                values[option["param"]] = True
            elif i + 1 < len(words):
                values[option["param"]] = words[i + 1]
                i += 1
            else:
                raise Failure("usage_error", f"{word} に値を指定してください。", exit_code=2)
        elif word.startswith("--"):
            raise Failure("usage_error", f"gui {name} に {word} はありません。", exit_code=2)
        else:
            positional.append(word)
        i += 1
    arguments = spec["arguments"]
    if len(positional) > len(arguments):
        raise Failure("usage_error", f"gui {name} の引数が多すぎます：{positional[len(arguments)]}", exit_code=2)
    for argument, value in zip(arguments, positional):
        values[argument["param"]] = value
    for argument in arguments[len(positional):]:
        if argument["required"]:
            raise Failure("usage_error", f"gui {name} に {argument['param']} を指定してください。", exit_code=2)
    return values


def run(name: str, words: list[str]) -> object:
    values = parse(name, words)
    if name == "login":
        return login(bool(values.get("switch")))
    if name == "scope":
        return scope(values["scope"])
    if name == "pick-folder":
        return {"path": pick_folder(values.get("title") or "フォルダを選ぶ", values.get("initial") or "")}
    if name == "shortcut":
        return shortcut(values.get("module") or "", values.get("place") or "", bool(values.get("pick")))
    if name == "quit":
        return quit_gui()
    return update(values.get("ref") or "")


# 端末の窓（gh のログインは、ブラウザーでの承認と対話が要る） ------------------------------------------------------------
def _terminal(command: str) -> dict:
    if os.name != "nt":
        raise Failure("not_supported", f"端末で {command} を実行してください。")
    subprocess.Popen(["cmd", "/c", f"{command} & pause"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    return {"command": command}


def login(switch: bool) -> dict:
    return _terminal("gh auth switch -h github.com" if switch else "gh auth login -h github.com -w -s project")


def scope(name: str) -> dict:
    if name not in SCOPES:
        raise Failure("usage_error", f"足せる権限は {'・'.join(SCOPES)} です：{name}", exit_code=2)
    return {**_terminal(f"gh auth refresh -h github.com -s {name}"), "scope": name}


# フォルダを選ぶ窓 --------------------------------------------------------------------------------------------------
_PICK = r"""
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk(); root.overrideredirect(True); root.geometry("0x0+0+0"); root.attributes("-topmost", True)
root.lift(); root.focus_force()   # 持ち主の窓を前に出しておく（隠すと、選ぶ窓が GUI の窓の後ろに出る）
path = filedialog.askdirectory(parent=root, title=sys.argv[1], initialdir=sys.argv[2] or None, mustexist=False)
print(path or "")
"""


def pick_folder(title: str, initial: str = "") -> str:
    """フォルダを選ぶ窓（OS の標準）。選ばなければ空。"""
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe" and python.with_name("python.exe").is_file():
        python = python.with_name("python.exe")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    done = subprocess.run([str(python), "-c", _PICK, title, initial if initial and Path(initial).is_dir() else ""],
                          capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, creationflags=flags)
    return done.stdout.strip().replace("\\", "/")


# ショートカット ------------------------------------------------------------------------------------------------------
def module_app_id(root: str | Path) -> str:
    """モジュールの窓の AppUserModelID（タスクバーで、モジュールごとに別のアプリ）。eco_gui/electron/main.js の moduleAppId と、
    今までの GUI（app.py の module_app_id）と同じ作り方。"""
    key = str(root).replace("\\", "/").rstrip("/").lower()
    return "ECOBuild.Module." + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def module_type(root: Path) -> str:
    """モジュールの型（.ecobuild/ecobuild.toml の [module] type）。読めなければ空。"""
    try:
        text = (root / ".ecobuild" / "ecobuild.toml").read_text(encoding="utf-8")
    except OSError:
        return ""
    table = next((t for t in re.split(r"^\s*\[", text, flags=re.M) if t.startswith("module]")), "")
    found = re.search(r'^\s*type\s*=\s*"([^"]*)"', table, flags=re.M)
    return found.group(1) if found else ""


def type_icons(ecobuild: list[str] | None = None) -> dict[str, str]:
    """型 → アイコン（.ico）の場所（ecobuild module types の icon_ico）。読めなければ空。"""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        done = subprocess.run([*(ecobuild or [os.environ.get("ECOBUILD_GUI_ECOBUILD") or "ecobuild"]), "module", "types", "--json"],
                              capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=60,
                              creationflags=flags)
        result = json.loads(done.stdout.strip().splitlines()[-1]).get("result") or []
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return {}
    return {str(t["name"]): str(t["icon_ico"]) for t in result if isinstance(t, dict) and t.get("name") and t.get("icon_ico")}


def module_icon(root: Path) -> str:
    """モジュールの窓・ショートカットのアイコン：型のもの（なければ module.ico）。"""
    found = type_icons().get(module_type(root), "")
    return found if found and Path(found).is_file() else str(HERE / "module.ico")


def _venv() -> Path:
    """ショートカットが使う venv：今の Python のもの（GUIFrameWork の入った venv）。なければインストーラーが作る場所。"""
    import eco_gui_setup

    here = Path(sys.prefix)
    return here if eco_gui_setup.python_of(here, windowless=True).is_file() and sys.prefix != sys.base_prefix else eco_gui_setup.default_venv()


def _last_place_file() -> Path:
    import eco_gui_setup

    return eco_gui_setup.default_venv().parent / "shortcut-place.txt"


def shortcut(module: str, place: str = "", pick: bool = False) -> dict:
    import eco_gui_setup

    if os.name != "nt":
        raise Failure("not_supported", "ショートカットは Windows でのみ作成できます。")
    if not module:
        made = [str(eco_gui_setup.make_shortcut(p, _venv())) for p in eco_gui_setup.shortcut_places() if p.is_dir()]
        return {"made": made, "message": "ショートカットを作りました：" + "、".join(Path(p).name for p in made)}
    root = Path(module).expanduser().resolve()
    if not root.is_dir():
        raise Failure("not_found", f"フォルダが見つかりません：{module}")
    if pick:
        try:
            last = _last_place_file().read_text(encoding="utf-8").strip()
        except OSError:
            last = ""
        place = pick_folder(f"{root.name} のショートカットを作るフォルダを選ぶ", last)
        if not place:
            return {"made": [], "message": "ショートカットは作りませんでした（フォルダを選びませんでした）。"}
        try:
            _last_place_file().parent.mkdir(parents=True, exist_ok=True)
            _last_place_file().write_text(place, encoding="utf-8")
        except OSError:
            pass
    folder = Path(place) if place else next((p for p in eco_gui_setup.shortcut_places() if p.is_dir()), None)
    if folder is None or not folder.is_dir():
        raise Failure("not_found", f"フォルダが見つかりません：{place}")
    try:
        link = eco_gui_setup.make_module_shortcut(root, folder, _venv(), module_icon(root), module_app_id(root))
    except RuntimeError as error:
        raise Failure("gui_error", str(error)) from None
    return {"made": [str(link)], "message": f"ショートカットを作りました：{link}"}


# 終える・起動し直す --------------------------------------------------------------------------------------------------
def quit_gui() -> dict:
    """窓をすべて閉じ（Electron のアプリも、窓がなくなると終わる）、中継地点を止める。"""
    import next_gui

    try:
        windows = (next_gui.display("windows", timeout=20) or {}).get("windows") or []
    except next_gui.Refused:
        return {"stopped": False}
    for window in windows:
        if isinstance(window, dict) and window.get("id") and not window.get("parent"):
            try:
                next_gui.display("close", options=("--window", str(window["id"])), timeout=20)
            except next_gui.Refused:
                pass
    try:
        next_gui.display("stop", timeout=20)
    except next_gui.Refused:
        pass
    return {"stopped": True}


def update(ref: str = "") -> dict:
    """ecobuild installer update [--ref <版>]。入れ直しが始まったら、切り離したプロセスが GUI を終え、インストーラーの窓が
    閉じたら GUI を起動し直す（入れ替えたファイルで動くように）。"""
    command = [os.environ.get("ECOBUILD_GUI_ECOBUILD") or "ecobuild", "installer", "update", *(["--ref", ref] if ref else []), "--json"]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        done = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                              creationflags=flags)
        document = json.loads(done.stdout.strip().splitlines()[-1])
    except (OSError, ValueError, IndexError) as error:
        raise Failure("gui_error", f"ecobuild installer update を実行できませんでした：{error}") from None
    if not document.get("ok"):
        error = document.get("error") or {}
        raise Failure(str(error.get("code") or "error"), str(error.get("message") or "更新できませんでした。"), error.get("hint"))
    result = document.get("result") or {}
    if result.get("up_to_date"):
        return {**result, "message": "その版が入っています。" if ref else "最新です。"}
    _start_detached([sys.executable, str(Path(__file__).resolve()), "relaunch-after", str(int(result.get("process") or 0))])
    return {**result, "message": "更新を始めました。インストーラーの窓が閉じたら、GUI が起動し直します。"}


def _start_detached(command: list[str]) -> None:
    streams = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        subprocess.Popen(command, creationflags=0x00000008 | 0x00000200 | subprocess.CREATE_NO_WINDOW, close_fds=True, **streams)
    else:
        subprocess.Popen(command, start_new_session=True, **streams)


def _wait_for_process(pid: int) -> None:
    """pid が終わるまで待つ（最長2時間）。0・もうないなら待たない。"""
    if pid and os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x00100000, False, pid)   # SYNCHRONIZE
        if handle:
            kernel32.WaitForSingleObject(handle, 2 * 60 * 60 * 1000)
            kernel32.CloseHandle(handle)


def relaunch_after(pid: int) -> None:
    """（切り離したプロセスで）GUI を終え、インストーラー（pid）が終わったら、GUI が動いていなければ起動し直す
    （インストーラーも、動いていた GUI を開き直す。そのときは、そちらに任せる）。"""
    import next_gui

    time.sleep(2)   # 頼んだ画面に、実行の終わりが届くように
    quit_gui()
    _wait_for_process(pid)
    time.sleep(2)
    if not pid or next_gui.running():
        return
    import eco_gui_setup

    pythonw = eco_gui_setup.python_of(eco_gui_setup.default_venv(), windowless=True)
    python = pythonw if pythonw.is_file() else Path(sys.executable)
    _start_detached([str(python), str(HERE / "ECOBuildGUINext.pyw")])


if __name__ == "__main__":   # 切り離したプロセス：python next_commands.py relaunch-after <pid>
    sys.path.insert(0, str(HERE))
    if sys.argv[1:2] == ["relaunch-after"]:
        relaunch_after(int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 0)
