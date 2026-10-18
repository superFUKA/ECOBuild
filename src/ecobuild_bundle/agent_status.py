"""画面を持つアプリ（GUI のエージェントの窓）へ、エージェント（Claude Code）の状態を知らせる。

この端末で動かす（agent start --here）ときだけ使う。Claude Code に --settings で statusLine と Stop フックを渡し、
小さなスクリプト（REPORT）が、作業空間ごとの置き場所（ECOBUILD_HOME/agents/status/<コンテナの名前>）に書き出す：
- status.json：モデル・コンテキストの使用率・使用量の制限（5時間・週）・会話の ID（statusLine が受け取るもの）
- replied.json：返答が終わった時刻と、最後の返答の文（Stop フック）
置き場所は、端末の出力に見えない印（OSC 1337 の ECOBuildAgentStatus=<場所>）で知らせる（アプリはそれを拾う。
ほかの端末には何も見えない）。コンテナの中のエージェントは、この置き場所をマウントした所（INSIDE）に書く。
"""

from __future__ import annotations

import json
import sys
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
    data = json.load(sys.stdin)
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
if kind == "replied":
    message = data.get("last_assistant_message")
    write("replied.json", {"at": time.time(), "message": message if isinstance(message, str) else None})
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
    sys.stdout.write(" · ".join(parts))
'''


def directory(name: str) -> Path:
    """作業空間（コンテナの名前で表す）の置き場所。"""
    return _settings.home() / FOLDER / name


def prepare(name: str) -> Path:
    """置き場所を用意し（前の状態は消す）、スクリプトを置く。"""
    folder = directory(name)
    folder.mkdir(parents=True, exist_ok=True)
    for old in ("status.json", "replied.json"):
        (folder / old).unlink(missing_ok=True)
    (folder / SCRIPT).write_text(REPORT, encoding="utf-8", newline="\n")
    return folder


def claude_settings(folder: str, python: str) -> str:
    """Claude Code の --settings に渡す JSON（folder・python：エージェントから見た置き場所と Python）。"""
    script = f'{python} "{folder}/{SCRIPT}"'
    return json.dumps({"statusLine": {"type": "command", "command": f"{script} statusline", "padding": 0},
                       "hooks": {"Stop": [{"hooks": [{"type": "command", "command": f"{script} replied"}]}]}},
                      ensure_ascii=False)


def announce(folder: Path) -> None:
    """端末の出力に、置き場所の見えない印を出す（端末でなければ出さない）。"""
    if sys.stdout.isatty():
        sys.stdout.write(MARK.format(folder.as_posix()))
        sys.stdout.flush()
