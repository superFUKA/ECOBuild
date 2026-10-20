"""画面を持つアプリ（GUI のエージェントの窓）へ、エージェント（Claude Code）の状態を知らせる。

この端末で動かす（agent start --here）ときだけ使う。Claude Code に --settings で statusLine と Stop フックを渡し、
小さなスクリプト（REPORT）が、作業空間ごとの置き場所（ECOBUILD_HOME/agents/status/<コンテナの名前>）に書き出す：
- status.json：モデル・コンテキストの使用率・使用量の制限（5時間・週）・会話の ID（statusLine が受け取るもの）
- replied.json：返答が終わった時刻と、最後の返答の文（Stop フック）
- prompted.json：発言を受け取った時刻（UserPromptSubmit フック。返答の終わりより新しければ作業中）
ECOBuild が書くもの：workspace.json（どの作業空間か）、inbox/（エージェントに届けるもの。put・take）、
running.json（エージェントを動かしているこのPCのプロセス。止まっているかを見る・止める）。
置き場所は、端末の出力に見えない印（OSC 1337 の ECOBuildAgentStatus=<場所>）で知らせる（アプリはそれを拾う。
ほかの端末には何も見えない）。コンテナの中のエージェントは、この置き場所をマウントした所（INSIDE）に書く。
画面を持つアプリがいない（新しい画面で起動した）ときは、受け箱を届けるのもフック（deliver）：返答が終わったとき
（Stop。届いたものがあれば続けて読ませる）と、人が発言したとき（UserPromptSubmit。発言に添える）。
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

from ecobuild import settings as _settings

FOLDER = Path("agents") / "status"
INSIDE = "/home/ubuntu/.ecobuild-status"   # コンテナの中から見た置き場所（container.start がマウントする）
SCRIPT = "report.py"
MARK = "\x1b]1337;ECOBuildAgentStatus={}\x07"
REPORT = r'''# ECOBuild が置く：Claude Code の statusLine・Stop フックが受け取った情報を、このフォルダに書き出す（標準ライブラリだけ）
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
kind = sys.argv[1] if len(sys.argv) > 1 else "statusline"
try:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))   # Windows でも UTF-8 として読む
except Exception:
    data = {}
def write(name, value):
    path = os.path.join(here, name)
    try:
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)
    except OSError:
        pass
def take_all():
    """受け箱のものを古い順にすべて取り出す（ほかが先に取ったものは飛ばす。status.take と同じ形）。"""
    inbox, found = os.path.join(here, "inbox"), []
    try:
        names = sorted(n for n in os.listdir(inbox) if n.endswith(".json"))
    except OSError:
        return found
    for name in names:
        path = os.path.join(inbox, name)
        taken = path[:-5] + ".taken"
        try:
            os.replace(path, taken)
            with open(taken, encoding="utf-8") as f:
                item = json.load(f)
        except (OSError, ValueError):
            continue
        finally:
            try:
                os.remove(taken)
            except OSError:
                pass
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            found.append(item["text"])
    return found
def out(value):
    sys.stdout.buffer.write(json.dumps(value, ensure_ascii=False).encode("utf-8"))
deliver = "deliver" in sys.argv[2:]
if kind == "replied":
    message = data.get("last_assistant_message")
    write("replied.json", {"at": time.time(), "message": message if isinstance(message, str) else None})
    if deliver and (texts := take_all()):   # 届いたものがあれば、返答を終えずに続けて読ませる
        write("prompted.json", {"at": time.time()})
        out({"decision": "block", "reason": "ECOBuild から届きました：\n\n" + "\n\n".join(texts)})
elif kind == "prompt":
    write("prompted.json", {"at": time.time()})
    if deliver and (texts := take_all()):   # 人の発言に添える
        out({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                    "additionalContext": "ECOBuild から届いていたもの：\n\n" + "\n\n".join(texts)}})
else:
    model = data.get("model") or {}
    window = data.get("context_window") or {}
    info = {"at": time.time(), "model": model.get("display_name") or model.get("id"),
            "context": window.get("used_percentage"), "limits": data.get("rate_limits"),
            "session": data.get("session_id"), "cwd": (data.get("workspace") or {}).get("current_dir") or data.get("cwd")}
    write("status.json", info)
    parts = [info["model"] or "Claude"]
    if info["context"] is not None:
        parts.append("ctx %d%%" % round(info["context"]))
    sys.stdout.buffer.write(" · ".join(parts).encode("utf-8"))
'''


def directory(name: str) -> Path:
    """作業空間（コンテナの名前で表す）の置き場所。"""
    return _settings.home() / FOLDER / name


WORKSPACE = "workspace.json"   # 置き場所の中：どの作業空間のエージェントか（係 serve が読む）
INBOX = "inbox"                # 置き場所の中：エージェントに届けるもの（言付け・作業役の知らせ）


def prepare(name: str, root: Path | None = None) -> Path:
    """置き場所を用意し（前の状態は消す。受け箱は残す：起動の前に届いたもの）、スクリプトを置く。
    root：作業空間の場所（記録する）。"""
    folder = directory(name)
    folder.mkdir(parents=True, exist_ok=True)
    for old in ("status.json", "replied.json", "prompted.json"):
        (folder / old).unlink(missing_ok=True)
    (folder / SCRIPT).write_text(REPORT, encoding="utf-8", newline="\n")
    if root is not None:
        _write(folder / WORKSPACE, {"root": str(Path(root))})
    return folder


def workspace_of(folder: Path) -> Path | None:
    """置き場所が、どの作業空間のエージェントのものか（記録がなければ None：オペレーター等）。"""
    data = read(Path(folder) / WORKSPACE)
    return Path(data["root"]) if isinstance(data, dict) and data.get("root") else None


def folders() -> list[Path]:
    """このPCの、エージェントの状態の置き場所すべて。"""
    root = _settings.home() / FOLDER
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


def read(file: Path):
    """JSON のファイル（読めなければ None）。"""
    try:
        return json.loads(Path(file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(file: Path, value) -> None:
    temporary = file.with_name(file.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, file)


_last_put = 0


def put(folder: Path, text: str, sender: str = "") -> Path:
    """エージェント（置き場所 folder）の受け箱に入れる。届けるのはエージェントを動かしている側（GUI の窓等）：
    待機中で入力欄が空のときに、古いものから1つずつ入力欄に送る。"""
    global _last_put
    inbox = Path(folder) / INBOX
    inbox.mkdir(parents=True, exist_ok=True)
    _last_put = max(time.time_ns(), _last_put + 1)   # 続けて入れたものの順を保つ（Windows の時計は刻みが粗い）
    file = inbox / f"{_last_put:020d}-{uuid.uuid4().hex[:8]}.json"
    _write(file, {"at": time.time(), "from": sender, "text": text})
    return file


def take(folder: Path) -> dict | None:
    """受け箱の一番古いものを取り出す（ほかが先に取ったものは飛ばす）。なければ None。"""
    inbox = Path(folder) / INBOX
    for file in sorted(inbox.glob("*.json")) if inbox.is_dir() else ():
        taken = file.with_suffix(".taken")
        try:
            os.replace(file, taken)
        except OSError:
            continue
        data = read(taken)
        taken.unlink(missing_ok=True)
        if isinstance(data, dict):
            return data
    return None


def forget_old(prefix: str, days: float = 1.0) -> None:
    """prefix で始まる置き場所のうち、しばらく使っていないもの（days 日より前）を消す（起動ごとに作るものの片付け）。"""
    import shutil
    import time
    root = _settings.home() / FOLDER
    if not root.is_dir():
        return
    for folder in root.glob(prefix + "*"):
        try:
            if time.time() - max(f.stat().st_mtime for f in [folder, *folder.iterdir()]) > days * 86400:
                shutil.rmtree(folder, ignore_errors=True)
        except (OSError, ValueError):
            pass


SETTINGS = "settings.json"   # Claude Code の --settings に渡すファイル（置き場所の中）
# 画面を持つアプリが動かすときの設定：音声入力（Space を押し続ける間だけ録音。送るのは人。アプリはキーのリピートで
# 押し続けをまねる）、入力欄に返答の候補を出さない（入力欄の文字を読むので、候補が混ざらないように）
VOICE = {"voice": {"enabled": True, "mode": "hold", "autoSubmit": False}, "promptSuggestionEnabled": False}


def _host_language() -> str:
    """このPCの Claude Code の設定（~/.claude/settings.json）の language（なければ空）。"""
    try:
        found = json.loads((Path.home() / ".claude" / "settings.json").read_text(encoding="utf-8")).get("language")
    except (OSError, ValueError, AttributeError):
        return ""
    return found if isinstance(found, str) else ""


def claude_settings(folder: str, python: str, base: dict | None = None, *, app: bool = True) -> str:
    """Claude Code の --settings に渡す設定の JSON（folder・python：エージェントから見た置き場所と Python）。
    base：一緒に渡す設定（許可・ほかのフック。statusLine と Stop フックを足す）。app：画面を持つアプリが動かす
    （音声入力を使い、受け箱はアプリが届ける）。そうでなければ、受け箱はフックが届ける（deliver）。"""
    script = f'{python} "{folder}/{SCRIPT}"'
    settings = json.loads(json.dumps(base or {}))
    if app:
        settings.update(VOICE)
        language = _host_language()
        if language and "language" not in settings:
            settings["language"] = language     # 音声入力の言語（設定がなければ英語になる）：このPCの Claude の設定に合わせる
    deliver = "" if app else " deliver"
    settings["statusLine"] = {"type": "command", "command": f"{script} statusline", "padding": 0}
    hooks = settings.setdefault("hooks", {})
    hooks["Stop"] = [*hooks.get("Stop", []), {"hooks": [{"type": "command", "command": f"{script} replied{deliver}"}]}]
    hooks["UserPromptSubmit"] = [*hooks.get("UserPromptSubmit", []),   # 作業中か（と、アプリがいなければ受け箱を届ける）
                                 {"hooks": [{"type": "command", "command": f"{script} prompt{deliver}"}]}]
    return json.dumps(settings, ensure_ascii=False)


def settings_argument(host: Path, folder: str, python: str, base: dict | None = None, *, app: bool = True) -> str:
    """設定を置き場所（host：このPCの場所）にファイルで書き、エージェントから見たその場所（folder の中）を返す。
    JSON をそのまま引数にしない（Windows の claude.cmd は cmd.exe を通るので、" が崩れる）。"""
    (host / SETTINGS).write_text(claude_settings(folder, python, base, app=app), encoding="utf-8", newline="\n")
    return f"{folder}/{SETTINGS}"


def host_python() -> str:
    """このPCで動かすエージェントのフックが使う Python（この ecobuild の Python）。"""
    return '"' + Path(sys.executable).as_posix() + '"'


def announce(folder: Path) -> None:
    """端末の出力に、置き場所の見えない印を出す（端末でなければ出さない）。"""
    if sys.stdout.isatty():
        sys.stdout.write(MARK.format(folder.as_posix()))
        sys.stdout.flush()


# ---- 動いているか・様子 ----------------------------------------------------------------------------------------
RUNNING = "running.json"   # 置き場所の中：エージェントを動かしているこのPCのプロセス（pid）と起動した時刻
WORKING, IDLE, STOPPED, UNKNOWN = "working", "idle", "stopped", "unknown"
STATE_NAMES = {WORKING: "作業中", IDLE: "待機中", STOPPED: "止まっている", UNKNOWN: "不明"}


def started(folder: Path, pid: int) -> None:
    """エージェントを動かすプロセス pid を覚える（起動したとき）。"""
    _write(Path(folder) / RUNNING, {"pid": pid, "at": time.time()})


def ended(folder: Path, pid: int) -> None:
    """プロセス pid が終わった（同じ置き場所を新しく起動したものが覚えていれば消さない）。"""
    data = read(Path(folder) / RUNNING)
    if isinstance(data, dict) and data.get("pid") == pid:
        (Path(folder) / RUNNING).unlink(missing_ok=True)


def alive(pid: int) -> bool:
    """このPCのプロセス pid が動いているか。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop(pid: int) -> None:
    """プロセス pid を、その子（エージェント・コンテナの中への exec）ごと止める。"""
    import signal
    import subprocess
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def running_pid(folder: Path) -> int | None:
    """置き場所のエージェントを動かしているプロセス（動いていなければ None）。"""
    data = read(Path(folder) / RUNNING)
    pid = data.get("pid") if isinstance(data, dict) else None
    return pid if isinstance(pid, int) and alive(pid) else None


def activity(folder: Path) -> dict:
    """置き場所のエージェントの様子：state（作業中・待機中・止まっている・不明）、since（その様子になった時刻）、
    last_reply（最後の返答の頭）、replied_at、context（コンテキストの使用率）、waiting（受け箱に届いていないもの）。"""
    folder = Path(folder)
    running, replied, prompted, info = (read(folder / name) for name in (RUNNING, "replied.json", "prompted.json",
                                                                          "status.json"))
    running, replied, prompted, info = (x if isinstance(x, dict) else {} for x in (running, replied, prompted, info))
    started_at, replied_at, prompted_at = (x.get("at") if isinstance(x.get("at"), (int, float)) else None
                                           for x in (running, replied, prompted))
    if not running:
        state, since = (UNKNOWN, None) if info or replied else (STOPPED, None)   # 記録のない起動（前の ECOBuild）
    elif running_pid(folder) is None:
        state, since = STOPPED, None
    else:
        began = max(x for x in (started_at, prompted_at) if x is not None) if (started_at or prompted_at) else None
        working = replied_at is None or (began is not None and began > replied_at)
        state, since = (WORKING, began) if working else (IDLE, replied_at)
    message = replied.get("message") if isinstance(replied.get("message"), str) else ""
    inbox = folder / INBOX
    return {"state": state, "since": since, "replied_at": replied_at, "last_reply": " ".join(message.split())[:300],
            "context": info.get("context") if isinstance(info.get("context"), (int, float)) else None,
            "waiting": len(list(inbox.glob("*.json"))) if inbox.is_dir() else 0}
