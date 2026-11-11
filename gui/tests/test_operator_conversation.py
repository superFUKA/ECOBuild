"""オペレーターとの会話の記録（operator_kit.converse・conversation・forget）：ecobuild gui ask --continue・gui conversation・
gui conversation-new。エージェント（claude）は動かさない（返答の流れを偽のもので確かめる）。"""

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ecobuild_gui  # noqa: E402
import operator_kit  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOBUILD_GUI_HOME", str(tmp_path / "gui"))
    monkeypatch.setattr(operator_kit, "catalog", lambda where=None: {"commands": [], "types": {}})
    monkeypatch.setattr(operator_kit, "style", lambda: "")
    return tmp_path / "gui"


def _reply(text, session="s1", tools=()):
    events = [{"type": "system", "session_id": session}]
    for index, (name, given, failed) in enumerate(tools):
        events.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{index}", "name": name, "input": given}]}})
        events.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{index}", "is_error": failed, "content": "x"}]}})
    events.append({"type": "result", "result": text, "session_id": session})
    return [json.dumps(event, ensure_ascii=False) + "\n" for event in events]


@pytest.fixture
def agent(home, monkeypatch):
    """claude の代わり：受けた引数と文を覚え、決めた返答（stream-json）を1行ずつ返す。"""
    asked = []
    monkeypatch.setattr(operator_kit, "_command", lambda command, gui=None: ["claude"])

    def stream(args, folder, text, timeout, on_line):
        asked.append((args, text))
        lines = _reply(f"{text}、ですね", tools=[("mcp__ecobuild-gui__ecobuild_read", {"args": ["task", "list"], "dir": "C:/Calc"}, False),
                                                ("mcp__ecobuild-gui__gui_open", {"page": "tasks"}, True)])
        for line in lines:
            on_line(line)
        return "".join(lines), ""

    monkeypatch.setattr(operator_kit, "_stream", stream)
    return asked


def test_ask_continue_keeps_the_conversation(agent, monkeypatch, capsys):
    """--continue：このPCの会話の記録の続きとして話す。発言・返答・実行したコマンドが記録に残り、次は同じ会話で続く。"""
    assert ecobuild_gui.main(["conversation", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == {"session": None, "messages": [], "state": "idle", "doing": None,
                                                             "starting_for": None}
    monkeypatch.setattr(sys, "stdin", io.StringIO("タスクを見せて"))
    assert ecobuild_gui.main(["ask", "--continue", "--json", "--", "-"]) == 0      # 画面からの呼び方（文は標準入力）
    captured = capsys.readouterr()
    assert json.loads(captured.out)["result"]["text"] == "タスクを見せて、ですね"
    # 途中で使い始めた道具は、標準エラーに1行ずつ（画面の「実行中：…」）
    assert [json.loads(line) for line in captured.err.splitlines()] == [
        {"kind": "output", "text": "ecobuild -C C:/Calc task list", "stream": "stdout", "source": "tool"},
        {"kind": "output", "text": "ecobuild gui open --page tasks", "stream": "stdout", "source": "tool"}]
    assert "--resume" not in agent[0][0]
    assert ecobuild_gui.main(["ask", "次は？", "--continue", "--json"]) == 0
    assert agent[1][0][agent[1][0].index("--resume") + 1] == "s1" and agent[1][1] == "次は？"
    capsys.readouterr()
    assert ecobuild_gui.main(["conversation", "--json"]) == 0
    found = json.loads(capsys.readouterr().out)["result"]
    assert found["session"] == "s1" and found["state"] == "idle"
    assert [(m["role"], m["text"]) for m in found["messages"]] == [
        ("user", "タスクを見せて"), ("agent", "タスクを見せて、ですね"), ("user", "次は？"), ("agent", "次は？、ですね")]
    assert found["messages"][1]["actions"] == [{"command": "ecobuild -C C:/Calc task list", "ok": True},
                                               {"command": "ecobuild gui open --page tasks", "ok": False}]
    # 人向けの表示
    assert ecobuild_gui.main(["conversation"]) == 0
    text = capsys.readouterr().out
    assert "自分：タスクを見せて" in text and "  $ ecobuild gui open --page tasks（失敗）" in text and "（待機中）" in text
    # 新しい会話：記録が空になり、次は続きではない
    assert ecobuild_gui.main(["conversation-new", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["messages"] == []
    assert ecobuild_gui.main(["ask", "もう一度", "--continue", "--json"]) == 0
    assert "--resume" not in agent[2][0]


def test_ask_without_continue_leaves_the_record(agent, capsys):
    assert ecobuild_gui.main(["ask", "一覧", "--session", "s9", "--json"]) == 0
    assert agent[0][0][agent[0][0].index("--resume") + 1] == "s9"
    assert operator_kit.conversation()["messages"] == []
    capsys.readouterr()
    assert ecobuild_gui.main(["ask", "一覧", "--session", "s9", "--continue", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "usage_error"


def test_a_failed_ask_is_kept_as_a_failed_reply(home, monkeypatch, capsys):
    monkeypatch.setattr(operator_kit.shutil, "which", lambda name: None)
    assert ecobuild_gui.main(["ask", "一覧を見せて", "--continue", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "agent_not_found"
    found = operator_kit.conversation()
    assert found["state"] == "idle" and [m["role"] for m in found["messages"]] == ["user", "agent"]
    assert found["messages"][1]["ok"] is False and "claude が見つかりません" in found["messages"][1]["text"]


def test_the_conversation_tells_when_an_ask_is_waiting(agent, monkeypatch):
    """返答を待っている間は thinking と、実行中の道具。待っている間は、次の発言・新しい会話は断る。"""
    seen = []

    def stream(args, folder, text, timeout, on_line):
        on_line(_reply("x", tools=[("mcp__ecobuild-gui__ecobuild_read", {"args": ["status"]}, False)])[1])
        seen.append(operator_kit.conversation())
        with pytest.raises(operator_kit.Failure) as refused:
            operator_kit.converse("割り込み")
        seen.append(refused.value.code)
        with pytest.raises(operator_kit.Failure):
            operator_kit.forget()
        return "".join(_reply("終わり")), ""

    monkeypatch.setattr(operator_kit, "_stream", stream)
    operator_kit.converse("状態は？")
    assert seen[0]["state"] == "thinking" and seen[0]["doing"] == "ecobuild status" and seen[1] == "in_use"
    assert seen[0]["starting_for"] is None
    assert seen[0]["messages"][-1]["role"] == "user" and seen[0]["messages"][-1]["text"] == "状態は？"
    done = operator_kit.conversation()
    assert done["state"] == "idle" and [m["text"] for m in done["messages"]] == ["状態は？", "終わり"]
    # 待っていたプロセスが、返答を記録せずに消えた：待機中に戻る
    record = operator_kit._record()
    record["asking"] = {"pid": 2 ** 22 + 12344, "at": 0, "doing": None}
    operator_kit._keep(record)
    assert operator_kit.conversation()["state"] == "idle"


def test_the_conversation_is_starting_until_the_agent_answers(agent, monkeypatch, capsys):
    """エージェントを起動して、最初の出力が届くまでは starting（起動を待っている秒数付き）。届いたら thinking。"""
    seen = []

    def stream(args, folder, text, timeout, on_line):
        seen.append(operator_kit.conversation())
        assert ecobuild_gui.main(["conversation"]) == 0
        seen.append(capsys.readouterr().out)
        lines = _reply("起きました")
        on_line(lines[0])
        seen.append(operator_kit.conversation())
        return "".join(lines), ""

    monkeypatch.setattr(operator_kit, "_stream", stream)
    operator_kit.converse("起きて")
    assert seen[0]["state"] == "starting" and 0 <= seen[0]["starting_for"] < 60 and seen[0]["doing"] is None
    assert "（起動中…）" in seen[1]
    assert seen[2]["state"] == "thinking" and seen[2]["starting_for"] is None
    assert operator_kit.conversation()["state"] == "idle"


def test_the_record_keeps_only_the_last_messages(agent):
    record = operator_kit._record()
    record["messages"] = [{"role": "user", "text": str(n)} for n in range(operator_kit.KEEP + 20)]
    operator_kit._keep(record)
    kept = operator_kit.conversation()["messages"]
    assert len(kept) == operator_kit.KEEP and kept[-1]["text"] == str(operator_kit.KEEP + 19)


def test_the_stream_reads_line_by_line(home, tmp_path):
    """本物のプロセスで：標準入力の文を渡し、標準出力を1行ずつ受ける。"""
    script = tmp_path / "echo.py"
    script.write_text("import sys\ntext = sys.stdin.read()\nprint('a:' + text)\nprint('b')\nsys.stderr.write('err')\n", encoding="utf-8")
    lines = []
    output, errors = operator_kit._stream([sys.executable, str(script)], tmp_path, "hi", 30, lines.append)
    assert lines == ["a:hi\n", "b\n"] and output == "a:hi\nb\n" and errors == "err"


def test_the_screen_side_reads_the_commands_from_the_catalog():
    """新しい GUI（eco_gui）のつなぎは、拡張コマンドの形を ecobuild の一覧（extensions の commands：拡張コマンドが
    自分で答えた形）から読む。一覧にないとき（まだ置かれていない・古い ecobuild）は、同じ GUI の ecobuild_gui.py に聞く。"""
    pytest.importorskip("guiframework")
    from eco_gui.backend import EcobuildBackend, extension_commands

    assert ecobuild_gui.COMMANDS == ecobuild_gui.help_document()["commands"]
    other = {"name": "other", "path": "C:/bin/ecobuild-other.cmd", "summary": "", "commands": [
        {"name": "say", "path": "other say", "runnable": True, "effect": "read", "summary": "", "arguments": [], "options": [], "commands": []}]}
    listed = {"name": "gui", "path": "C:/bin/ecobuild-gui.cmd", "summary": "", "commands": [
        {"name": "conversation", "path": "gui conversation", "runnable": True, "effect": "read", "arguments": [], "options": []}]}
    assert [g["name"] for g in extension_commands({"extensions": [other, listed, {"name": "plain", "commands": []}]})] == ["other", "gui"]
    assert extension_commands({"extensions": [listed]})[0]["commands"] == listed["commands"]      # 一覧にあれば、一覧のもの
    assert extension_commands({"extensions": []}) == [{"name": "gui", "path": "gui", "runnable": False, "effect": None,
                                                       "commands": ecobuild_gui.COMMANDS}]              # なければ、GUI の口に聞く
    assert extension_commands({}) == []                                                            # 拡張コマンドを受けない ecobuild
    backend = EcobuildBackend(["ecobuild"])
    backend.ask = lambda argv: {"ok": True, "result": {"commands": [], "types": {}, "extensions": [
        other, {"name": "gui", "path": "C:/bin/ecobuild-gui.cmd", "summary": "", "commands": ecobuild_gui.COMMANDS}]}}
    specs = backend.commands()
    assert specs["other say"]["weight"] == "read"
    assert specs["gui ask"]["weight"] == "change" and specs["gui conversation"]["weight"] == "read"
    args = {"text": "1行目\n2行目", "continue": True}
    assert backend.command_line("gui ask", args, ["yes"]) == ["ecobuild", "gui", "ask", "--continue", "--json", "--", "-"]
    assert backend.standard_input("gui ask", args) == "1行目\n2行目"
    assert backend.command_line("gui conversation-new", {}) == ["ecobuild", "gui", "conversation-new", "--json"]
