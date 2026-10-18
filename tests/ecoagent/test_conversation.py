"""ecoagent.ask・kit：画面を開かずに1回話しかける（本物のエージェントは起動せず、出力の読み方と渡す引数を確かめる）。"""

import json
import subprocess

import pytest

import ecoagent
from ecoagent import conversation, kit

EVENTS = [
    {"type": "system", "subtype": "init", "session_id": "s1"},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                                                   "input": {"command": "tool list"}}]}},
    {"type": "system", "subtype": "permission_denied", "message": "requires approval"},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "a\nb"}]}},
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "2件です。"}]}},
    {"type": "result", "subtype": "success", "is_error": False, "result": "2件です。", "session_id": "s1"},
]


def _output(events=EVENTS):
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in events)


def test_parse_reads_the_reply_and_the_commands():
    reply = conversation.parse(_output() + "\nnot json")
    assert reply == ecoagent.Reply("s1", "2件です。", True, (ecoagent.Action("Bash", "tool list", True, "a\nb"),))
    assert conversation.parse(_output(EVENTS[:1])) is None


def test_ask_passes_the_prompt_session_and_settings(tmp_path, monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, _output(), "")

    monkeypatch.setattr(conversation.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(conversation.subprocess, "run", run)
    made = kit.prepare(tmp_path, "指示", allow=("Bash(tool:*)",), guard="tool guard")
    reply = ecoagent.ask(tmp_path, "一覧", session="s0", settings=made.settings)
    args, kwargs = calls[0]
    assert args[:3] == ["/bin/claude", "-p", "--output-format"] and kwargs["input"] == "一覧"
    assert args[args.index("--resume") + 1] == "s0" and args[args.index("--settings") + 1] == str(made.settings)
    assert kwargs["cwd"] == tmp_path.resolve() and reply.session == "s1"


def test_ask_without_a_result(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(conversation.subprocess, "run",
                        lambda args, **kw: subprocess.CompletedProcess(args, 1, "", "ログインしてください"))
    with pytest.raises(ecoagent.AgentError) as raised:
        ecoagent.ask(tmp_path, "一覧")
    assert raised.value.code == ecoagent.ErrorCode.ASK_FAILED and "ログイン" in raised.value.message
    with pytest.raises(ecoagent.AgentError) as raised:
        ecoagent.ask(tmp_path, "  ")
    assert raised.value.code == ecoagent.ErrorCode.EMPTY_PROMPT


def test_kit_writes_instructions_and_settings(tmp_path):
    made = kit.prepare(tmp_path / "op", "# 指示", allow=("Bash(tool:*)",), guard='"C:/bin/tool" guard')
    assert made.instructions.read_text(encoding="utf-8") == "# 指示\n"
    settings = json.loads(made.settings.read_text(encoding="utf-8"))
    assert settings["permissions"] == {"allow": ["Bash(tool:*)"], "deny": ["Edit", "Write", "NotebookEdit"]}
    hook = settings["hooks"]["PreToolUse"][0]
    assert hook["matcher"] == "Bash|PowerShell" and hook["hooks"][0]["command"] == '"C:/bin/tool" guard'
