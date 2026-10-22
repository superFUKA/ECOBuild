"""画面を持つアプリ（GUI のエージェントの窓）へ、エージェント（Claude Code）の状態を知らせる。

この端末で動かす（agent start --here）ときだけ使う。Claude Code に --settings で statusLine と Stop フックを渡し、
小さなスクリプト（REPORT）が、エージェントごとの置き場所（ECOBUILD_HOME/agents/status/<コンテナの名前>/<ID>）に書き出す：
- status.json：モデル・コンテキストの使用率・使用量の制限（5時間・週）・会話の ID（statusLine が受け取るもの）
- replied.json：返答が終わった時刻と、最後の返答の文（Stop フック）
- prompted.json：発言を受け取った時刻（UserPromptSubmit フック。返答の終わりより新しければ作業中）
ECOBuild が書くもの：agent.json（エージェントの記録。agents）、workspace.json（どの作業空間か）、inbox/（エージェントに
届けるもの。put・take）、
running.json（エージェントを動かしているこのPCのプロセス。止まっているかを見る・止める）。
置き場所は、端末の出力に見えない印（OSC 1337 の ECOBuildAgentStatus=<場所>）で知らせる（アプリはそれを拾う。
ほかの端末には何も見えない）。コンテナにはその作業空間の置き場所（<コンテナの名前>）をマウントし（INSIDE）、中の
エージェントは環境変数 ECOBUILD_AGENT_ID で自分の下のフォルダ（INSIDE/<ID>）を知る。
画面を持つアプリがいない（新しい画面で起動した）ときは、受け箱を届けるのもフック（deliver）：返答が終わったとき
（Stop。届いたものがあれば続けて読ませる）、人が発言したとき（UserPromptSubmit。発言に添える）、作業中に道具を使い
終えたとき（PostToolUse。返答を止めずに添える）。
アプリ用の起動（係が持つ。ecobuild_agent.app）では、statusLine・フックは使わない：係が出来事（events.jsonl）を読んで
様子（state.json）・返答の終わり（replied.json）を書き、受け箱を標準入力へ届ける。running.json の mode が app。
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

from ecobuild import fsutil as _fsutil
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
def take_all(session=""):
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
            if session and item.get("owner") not in (None, "", session):   # ほかの会話宛て：戻す
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(item, f, ensure_ascii=False)
                except OSError:
                    pass
                continue
            found.append(item["text"])
    return found
def out(value):
    sys.stdout.buffer.write(json.dumps(value, ensure_ascii=False).encode("utf-8"))
deliver = "deliver" in sys.argv[2:]
session = data.get("session_id") if isinstance(data.get("session_id"), str) else ""
if kind == "replied":
    message = data.get("last_assistant_message")
    texts = take_all(session) if deliver else []   # 届いたものがあれば、返答を終えずに続けて読ませる
    now = time.time()
    entry = {"at": now, "message": message if isinstance(message, str) else None, **({"continued": len(texts)} if texts else {})}
    try:   # 返答の終わりの記録（追記：続けて2回終わっても数え落とさない）
        with open(os.path.join(here, "replied.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": now, **({"continued": len(texts)} if texts else {})}) + "\n")
    except OSError:
        pass
    write("replied.json", entry)
    if texts:
        write("prompted.json", {"at": time.time()})
        out({"decision": "block", "reason": "ECOBuild から届きました：\n\n" + "\n\n".join(texts)})
elif kind == "midturn":   # 道具を使い終えるたび（PostToolUse）：作業中でも、届いたものを返答を止めずに添える
    if deliver and (texts := take_all(session)):
        out({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                    "additionalContext": "ECOBuild から届きました（作業中に届いたもの）：\n\n" + "\n\n".join(texts)}})
elif kind == "prompt":
    write("prompted.json", {"at": time.time()})
    if deliver and (texts := take_all(session)):   # 人の発言に添える
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


AGENT_VARIABLE = "ECOBUILD_AGENT_ID"   # コンテナの中のエージェントの環境：自分の ID（置き場所 INSIDE/<ID>）


def place(name: str) -> Path:
    """名前の置き場所（ECOBUILD_HOME/agents/status/<name>）：作業空間（コンテナの名前）ごとのフォルダ。エージェントの
    置き場所はこの下（<ID>）。オペレーター等、作業空間のエージェントでないものは、ここをそのまま使う。"""
    return _settings.home() / FOLDER / name


def directory(agent_id: str) -> Path | None:
    """エージェント（ID）の置き場所を探す（なければ None）。"""
    root = _settings.home() / FOLDER
    if not agent_id or "/" in agent_id or "\\" in agent_id or agent_id.startswith("."):
        return None
    try:
        return next((folder for folder in root.glob(f"*/{agent_id}") if folder.is_dir()), None)
    except OSError:
        return None


def create_directory(workspace_root: Path, agent_id: str) -> Path:
    """作業空間 workspace_root のエージェント（ID）の置き場所を作る（コンテナの名前の下。中から INSIDE/<ID> で見える）。"""
    import ecobuild_container as container
    folder = place(container.name(Path(workspace_root))) / agent_id
    folder.mkdir(parents=True, exist_ok=True)
    if workspace_of(folder) != Path(workspace_root):
        _write(folder / WORKSPACE, {"root": str(Path(workspace_root))})
    return folder


def inside(agent_id: str) -> str:
    """コンテナの中から見た、エージェント（ID）の置き場所。"""
    return f"{INSIDE}/{agent_id}"


def own_directory() -> Path | None:
    """コンテナの中で動いているエージェントの、自分の置き場所（環境変数 AGENT_VARIABLE。外・分からなければ None）。"""
    import ecobuild_container as container
    agent_id = os.environ.get(AGENT_VARIABLE, "").strip()
    return Path(inside(agent_id)) if agent_id and os.environ.get(container.INSIDE) else None


WORKSPACE = "workspace.json"   # 置き場所の中：どの作業空間のエージェントか（係 serve が読む）
INBOX = "inbox"                # 置き場所の中：エージェントに届けるもの（言付け・子の知らせ）


def prepare(folder: Path | str, root: Path | None = None) -> Path:
    """置き場所を用意し（前の状態は消す。受け箱は残す：起動の前に届いたもの）、スクリプトを置く。folder：エージェントの
    置き場所（文字なら名前の置き場所 place）。root：作業空間の場所（記録する）。"""
    folder = place(folder) if isinstance(folder, str) else Path(folder)
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
    """このPCの、作業空間のエージェントの置き場所すべて（<コンテナの名前>/<ID>。前の版の直下のものは入れない）。"""
    root = _settings.home() / FOLDER
    try:
        return sorted(p for p in root.glob(f"*/{ID_GLOB}") if p.is_dir())
    except OSError:
        return []


ID_GLOB = "a-??????????"   # エージェントの ID の形（agents.ID_PREFIX と 16進の10文字）


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


REPLIES = "replied.jsonl"   # 置き場所の中：返答の終わりの記録（1回1行の追記。replied.json は最後の1回だけ）
NOTICE = "notice"           # 受け箱のものの種類：子の返答の終わりの知らせ（同じ子の古いものは新しいものにまとめる）
_last_put = 0


def put(folder: Path, text: str, sender: str = "", owner: str = "", kind: str = "") -> Path:
    """エージェント（置き場所 folder）の受け箱に入れる。届けるのはエージェントを動かしている側（GUI の窓等）：
    待機中で入力欄が空のときに、古いものから1つずつ入力欄に送る。
    owner：宛先の会話の ID（同じ作業空間に会話が複数あるとき、その会話にだけ届ける。空なら誰にでも）。
    kind：種類（NOTICE 等。forget_from で選んで出す）。"""
    global _last_put
    inbox = Path(folder) / INBOX
    inbox.mkdir(parents=True, exist_ok=True)
    _last_put = max(time.time_ns(), _last_put + 1)   # 続けて入れたものの順を保つ（Windows の時計は刻みが粗い）
    file = inbox / f"{_last_put:020d}-{uuid.uuid4().hex[:8]}.json"
    _write(file, {"at": time.time(), "from": sender, "text": text, **({"owner": owner} if owner else {}),
                  **({"kind": kind} if kind else {})})
    return file


def forget_from(folder: Path, sender: str, kind: str = "", *, remove: bool = True) -> int:
    """受け箱の、sender から入れたまだ届いていないもの（kind を渡せばその種類だけ）を出す。出した数（remove=False なら
    出さずに数えるだけ）。"""
    inbox = Path(folder) / INBOX
    count = 0
    for file in sorted(inbox.glob("*.json")) if inbox.is_dir() else ():
        data = read(file)
        if not isinstance(data, dict) or data.get("from") != sender or (kind and data.get("kind") != kind):
            continue
        if not remove:
            count += 1
            continue
        try:
            file.unlink()
            count += 1
        except OSError:
            pass
    return count


def replies(folder: Path) -> int:
    """置き場所のエージェントが返答を終えた回数（REPLIES の行の数。言付けを受け取って続けたものも数える）。"""
    try:
        return len((Path(folder) / REPLIES).read_text(encoding="utf-8").splitlines())
    except OSError:
        return 0


def write_reply(folder: Path, message: str, continued: int = 0) -> None:
    """返答の終わりを書く（replied.json と、追記の REPLIES）。continued：受け取って続けた言付けの数（返答を終えていない）。"""
    now = time.time()
    extra = {"continued": continued} if continued else {}
    try:
        with open(Path(folder) / REPLIES, "a", encoding="utf-8") as file:
            file.write(json.dumps({"at": now, **extra}) + "\n")
    except OSError:
        pass
    _write(Path(folder) / "replied.json", {"at": now, "message": message, **extra})


def item_id(file: Path) -> str:
    """受け箱に入れたもの（put の結果）の番号：ファイル名の後ろの印（8文字）。"""
    return Path(file).stem.rsplit("-", 1)[-1]


def waiting_ids(folder: Path) -> set[str]:
    """受け箱にあって、まだ届いていないものの番号。"""
    inbox = Path(folder) / INBOX
    return {item_id(file) for file in inbox.glob("*.json")} if inbox.is_dir() else set()


def withdraw(folder: Path, key: str) -> bool:
    """受け箱の、まだ届いていない番号 key のものを出す（取り消し）。出せたか（届いた後・ほかが取った後なら False）。"""
    inbox = Path(folder) / INBOX
    for file in inbox.glob(f"*-{key}.json") if inbox.is_dir() and key else ():
        try:
            file.unlink()
            return True
        except OSError:
            return False
    return False


def take(folder: Path, session: str = "") -> dict | None:
    """受け箱の一番古いものを取り出す（ほかが先に取ったものは飛ばす）。なければ None。
    session：会話の ID（ほかの会話宛て〔owner〕のものは取らない。空なら全部）。"""
    inbox = Path(folder) / INBOX
    for file in sorted(inbox.glob("*.json")) if inbox.is_dir() else ():
        if session and (head := read(file)) and isinstance(head, dict) and head.get("owner") not in (None, "", session):
            continue
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


def claude_settings(folder: str, python: str, base: dict | None = None, *, app: bool = True,
                    streamed: bool = False) -> str:
    """Claude Code の --settings に渡す設定の JSON（folder・python：エージェントから見た置き場所と Python）。
    base：一緒に渡す設定（許可・ほかのフック。statusLine と Stop フックを足す）。app：画面を持つアプリが動かす
    （音声入力を使い、受け箱はアプリが届ける）。そうでなければ、受け箱はフックが届ける（deliver）。
    streamed：アプリ用の起動（係が出来事を読む。statusLine・返答の終わり・受け箱のフックは付けない）。"""
    script = f'{python} "{folder}/{SCRIPT}"'
    settings = json.loads(json.dumps(base or {}))
    hooks = settings.setdefault("hooks", {})
    if streamed:
        return json.dumps(_without_empty(settings, hooks), ensure_ascii=False)
    if app:
        settings.update(VOICE)
        language = _host_language()
        if language and "language" not in settings:
            settings["language"] = language     # 音声入力の言語（設定がなければ英語になる）：このPCの Claude の設定に合わせる
    deliver = "" if app else " deliver"
    settings["statusLine"] = {"type": "command", "command": f"{script} statusline", "padding": 0}
    hooks["Stop"] = [*hooks.get("Stop", []), {"hooks": [{"type": "command", "command": f"{script} replied{deliver}"}]}]
    hooks["UserPromptSubmit"] = [*hooks.get("UserPromptSubmit", []),   # 作業中か（と、アプリがいなければ受け箱を届ける）
                                 {"hooks": [{"type": "command", "command": f"{script} prompt{deliver}"}]}]
    if not app:   # アプリがいなければ、作業中に届いたものも道具を使い終えるたびに届ける
        hooks["PostToolUse"] = [*hooks.get("PostToolUse", []),
                                {"hooks": [{"type": "command", "command": f"{script} midturn{deliver}"}]}]
    return json.dumps(_without_empty(settings, hooks), ensure_ascii=False)


def _without_empty(settings: dict, hooks: dict) -> dict:
    if not hooks:
        settings.pop("hooks", None)
    return settings


def settings_argument(host: Path, folder: str, python: str, base: dict | None = None, *, app: bool = True,
                      streamed: bool = False) -> str:
    """設定を置き場所（host：このPCの場所）にファイルで書き、エージェントから見たその場所（folder の中）を返す。
    JSON をそのまま引数にしない（Windows の claude.cmd は cmd.exe を通るので、" が崩れる）。"""
    (host / SETTINGS).write_text(claude_settings(folder, python, base, app=app, streamed=streamed),
                                 encoding="utf-8", newline="\n")
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
RUNNING = "running.json"   # 置き場所の中：エージェントを動かしているこのPCのプロセス（pid）と起動した時刻・起動のしかた
STATE = "state.json"       # 置き場所の中：アプリ用の起動のエージェントの様子（係が出来事から書く。ecobuild_agent.app）
APP = "app"                # running.json の mode：アプリ用の起動（係が持つ）。なければ対話型
WORKING, IDLE, STOPPED, UNKNOWN = "working", "idle", "stopped", "unknown"
STATE_NAMES = {WORKING: "作業中", IDLE: "待機中", STOPPED: "止まっている", UNKNOWN: "不明"}


def started(folder: Path, pid: int, mode: str = "") -> None:
    """エージェントを動かすプロセス pid を覚える（起動したとき）。mode：起動のしかた（APP。対話型なら空）。"""
    _write(Path(folder) / RUNNING, {"pid": pid, "at": time.time(), **({"mode": mode} if mode else {})})


def ended(folder: Path, pid: int) -> None:
    """プロセス pid が終わった（同じ置き場所を新しく起動したものが覚えていれば消さない）。"""
    data = read(Path(folder) / RUNNING)
    if isinstance(data, dict) and data.get("pid") == pid:
        (Path(folder) / RUNNING).unlink(missing_ok=True)


def alive(pid: int) -> bool:
    """このPCのプロセス pid が動いているか。"""
    return _fsutil.process_alive(pid)


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


def running_mode(folder: Path) -> str | None:
    """置き場所のエージェントが動いていれば、その起動のしかた（APP か ""＝対話型）。動いていなければ None。"""
    if running_pid(folder) is None:
        return None
    data = read(Path(folder) / RUNNING)
    return str(data.get("mode") or "") if isinstance(data, dict) else ""


def session_of(folder: Path) -> str:
    """置き場所のエージェントの、最後の会話の ID（対話型は statusLine の status.json、アプリ用は state.json。新しい方）。"""
    found = []
    for data in (read(Path(folder) / "status.json"), read(Path(folder) / STATE)):
        if isinstance(data, dict) and isinstance(data.get("session"), str) and data["session"]:
            found.append((data.get("at") if isinstance(data.get("at"), (int, float)) else 0, data["session"]))
    return max(found, key=lambda pair: pair[0])[1] if found else ""


def activity(folder: Path) -> dict:
    """置き場所のエージェントの様子：state（作業中・待機中・止まっている・不明）、since（その様子になった時刻）、
    last_reply（最後の返答の頭）、replied_at、context（コンテキストの使用率）、waiting（受け箱に届いていないもの）。"""
    folder = Path(folder)
    if isinstance(running := read(folder / RUNNING), dict) and running.get("mode") == APP:
        return _app_activity(folder)
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


def _app_activity(folder: Path) -> dict:
    """アプリ用の起動のエージェントの様子（state.json。係が書く）。activity の項目に、mode・doing（今していること）・
    doing_at・usage（最後の返答の使用量）・limits（5時間・週の使用率）・denials（断られた権限）・error を足す。"""
    state = read(folder / STATE)
    state = state if isinstance(state, dict) else {}
    now = state.get("state") if running_pid(folder) is not None and state.get("state") in (WORKING, IDLE) else STOPPED
    number = lambda key: state.get(key) if isinstance(state.get(key), (int, float)) else None
    inbox = folder / INBOX
    return {"state": now, "since": number("since") if now != STOPPED else None, "replied_at": number("replied_at"),
            "last_reply": " ".join(str(state.get("last_reply") or "").split())[:300], "context": number("context"),
            "waiting": len(list(inbox.glob("*.json"))) if inbox.is_dir() else 0, "mode": APP,
            "doing": str(state.get("doing") or "") if now == WORKING else "", "doing_at": number("doing_at"),
            "usage": state.get("usage") if isinstance(state.get("usage"), dict) else None,
            "limits": state.get("limits") if isinstance(state.get("limits"), dict) else None,
            "denials": state.get("denials") if isinstance(state.get("denials"), list) else [],
            "error": str(state.get("error") or "")}
