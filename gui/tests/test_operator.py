"""オペレーター（operator_kit.py）：GUI の案内・操作係。できるのは読むことと GUI の操作だけ（ecobuild gui operator・ask・mcp --operator）。"""

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ecobuild_gui  # noqa: E402
import operator_kit  # noqa: E402

CATALOG = {
    "commands": [
        {"path": "status", "runnable": True, "effect": "read", "summary": "今の状態"},
        {"path": "task", "commands": [
            {"path": "task list", "runnable": True, "effect": "read", "summary": "タスクの一覧"},
            {"path": "task start", "runnable": True, "effect": "change", "summary": "タスクを始める"},
            {"path": "task finish", "runnable": True, "effect": "confirm", "summary": "タスクを終える"}]},
        {"path": "module settings", "runnable": True, "effect": "read", "summary": "モジュールの設定"},
        {"path": "container dockerfile", "runnable": True, "effect": "read", "summary": "Dockerfile"},
    ],
    "types": {"cpp": {"description": "C++", "commands": [{"path": "build", "runnable": True, "effect": "change", "summary": "ビルド"}]}},
}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOBUILD_GUI_HOME", str(tmp_path / "gui"))
    monkeypatch.setattr(operator_kit, "catalog", lambda where=None: CATALOG)
    monkeypatch.setattr(operator_kit, "style", lambda: "")
    return tmp_path / "gui"


@pytest.mark.parametrize("args, allowed", [
    (["status"], True),
    (["task", "list", "--all"], True),
    (["task", "start", "12"], False),           # 変える
    (["task", "finish", "12"], False),          # 確認が要る
    (["build"], False),                         # 型のコマンド（変える）
    (["task", "list", "--yes"], False),         # 重さを上げるオプション
    (["module", "settings", "--json"], True),
    (["module", "settings", "--name", "x"], False),   # 値を渡すと設定を変える
    (["container", "dockerfile", "--write", "-"], False),
    (["-C", "C:/Calc", "status"], False),       # 場所は dir で
    (["gui", "open"], False),                   # 一覧にない（拡張・知らないもの）
])
def test_only_read_commands_are_allowed(args, allowed):
    if allowed:
        assert operator_kit.read_command(args, CATALOG)
    else:
        with pytest.raises(operator_kit.Failure):
            operator_kit.read_command(args, CATALOG)


def test_the_operator_mcp_has_no_run_and_reads_only(home, monkeypatch, capsys):
    """オペレーター用の MCP：何でも実行できる ecobuild と agent-send はなく、見るだけの ecobuild_read がある。"""
    called = []
    monkeypatch.setattr(ecobuild_gui, "act", lambda name, params: called.append((name, params)) or {"ok": True, "result": "done"})
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "ecobuild_read", "arguments": {"args": ["task", "list"], "dir": "C:/M"}}},
             {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "ecobuild_read", "arguments": {"args": ["task", "start", "12"], "dir": "C:/M"}}},
             {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "ecobuild", "arguments": {"args": ["task", "start", "12"]}}},
             {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "gui_agent-send", "arguments": {"tab": 1, "text": "x"}}},
             {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "gui_open", "arguments": {"page": "tasks"}}}]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(json.dumps(x) for x in lines) + "\n"))
    assert ecobuild_gui.mcp(operator=True) == 0
    answers = {a["id"]: a for a in map(json.loads, capsys.readouterr().out.splitlines())}
    names = {t["name"] for t in answers[1]["result"]["tools"]}
    assert {"ecobuild_read", "ecobuild_commands", "gui_open", "gui_windows", "gui_agent-close"} <= names
    assert not {"ecobuild", "gui_run", "gui_agent-send"} & names
    assert answers[2]["result"]["isError"] is False
    assert "変える操作" in answers[3]["result"]["content"][0]["text"] and answers[3]["result"]["isError"]
    assert answers[4]["result"]["isError"] and answers[5]["result"]["isError"]
    assert answers[6]["result"]["isError"] is False
    assert called == [("run", {"args": ["task", "list"], "dir": "C:/M"}), ("open", {"page": "tasks"})]


def test_the_usual_mcp_keeps_every_tool(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"))
    assert ecobuild_gui.mcp() == 0
    names = {t["name"] for t in json.loads(capsys.readouterr().out)["result"]["tools"]}
    assert {"ecobuild", "gui_agent-send"} <= names and "ecobuild_read" not in names


def test_prepare_writes_the_kit(home):
    """一式：指示（見るだけのコマンドと GUI の操作）・許可（MCP だけ。シェル・編集は止める）・MCP の設定・文脈のフック。"""
    folder = operator_kit.prepare(style_text="語尾に「にゃ」を付けて")
    assert folder == home / "operator"
    text = (folder / "CLAUDE.md").read_text(encoding="utf-8")
    assert "- `task list`：タスクの一覧" in text and "`task start`" not in text and "`build`" not in text
    assert "`gui_open`" in text and "gui_agent-send" not in text and "`gui_run`" not in text
    assert "変える操作はしません" in text
    assert "## 話し方（ユーザーの指定）" in text and "語尾に「にゃ」を付けて" in text
    settings = json.loads((folder / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings["permissions"]["allow"] == ["mcp__ecobuild-gui"]
    assert {"Bash", "PowerShell", "Edit", "Write"} <= set(settings["permissions"]["deny"])
    assert settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"].endswith("operator-context")
    server = json.loads((folder / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["ecobuild-gui"]
    assert server["args"][-2:] == ["mcp", "--operator"] and server["args"][0].endswith("ecobuild_gui.py")
    assert "## 話し方" not in operator_kit.instructions(CATALOG)


def test_claude_gets_only_the_kit_tools(home, monkeypatch):
    operator_kit.prepare()
    monkeypatch.setattr(operator_kit.shutil, "which", lambda name: "C:/bin/claude.exe")
    args = operator_kit._command(("claude", "--model", "sonnet"))
    assert args[:3] == ["C:/bin/claude.exe", "--model", "sonnet"]
    assert "--strict-mcp-config" in args and args[args.index("--mcp-config") + 1].endswith("mcp.json")
    assert args[args.index("--effort") + 1] == "low"


def test_ask_without_the_agent_is_an_error(home, monkeypatch, capsys):
    monkeypatch.setattr(operator_kit.shutil, "which", lambda name: None)
    assert ecobuild_gui.main(["ask", "一覧を見せて", "--json"]) == 1
    document = json.loads(capsys.readouterr().out)
    assert document["ok"] is False and document["error"]["code"] == "agent_not_found"


def test_the_reply_lists_the_tools_used():
    """返答の途中で使った道具は、会話の窓の「実行したコマンド」に1行で出す。"""
    events = [
        {"type": "system", "session_id": "s1"},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "a", "name": "mcp__ecobuild-gui__ecobuild_read", "input": {"args": ["task", "list"], "dir": "C:/Calc"}},
            {"type": "tool_use", "id": "b", "name": "mcp__ecobuild-gui__gui_open", "input": {"page": "tasks"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "a", "content": "ok"},
                                                 {"type": "tool_result", "tool_use_id": "b", "is_error": True, "content": [{"type": "text", "text": "no"}]}]}},
        {"type": "result", "result": "開きました", "session_id": "s1"},
    ]
    reply = operator_kit.parse("\n".join(json.dumps(e) for e in events))
    assert reply["session"] == "s1" and reply["text"] == "開きました" and reply["ok"]
    assert [(a["command"], a["ok"]) for a in reply["actions"]] == [
        ("ecobuild -C C:/Calc task list", True), ("ecobuild gui open --page tasks", False)]
    assert operator_kit.parse('{"type": "system"}') is None


def test_operator_launches_or_shows_the_tab(monkeypatch):
    """gui operator：--state show／hide は GUI の操作（タブで開く・裏に戻す）、それ以外はオペレーターの起動。"""
    ran, acted = [], []
    monkeypatch.setattr(operator_kit, "run", lambda command: ran.append(command) or 0)
    monkeypatch.setattr(ecobuild_gui, "act", lambda name, params: acted.append((name, params)) or {})
    assert ecobuild_gui.main(["operator", "--here", "--agent", "claude --model sonnet"]) == 0
    assert ran == [("claude", "--model", "sonnet")]
    assert ecobuild_gui.main(["operator", "--state", "show"]) == 0
    assert acted == [("operator", {"state": "show"})]


def test_context_lists_the_workspaces(monkeypatch):
    monkeypatch.setattr(operator_kit, "ecobuild", lambda args, timeout=120: {"ok": True, "result": [
        {"path": "C:/ECO/Calc", "repository": "me/Calc", "branch": "task/12-x", "task": 12, "exists": True, "type": "cpp"},
        {"path": "C:/ECO/Gone", "exists": False}]})
    text = operator_kit.context()
    assert "- Calc：C:/ECO/Calc（task/12-x＝タスク #12・cpp）" in text and "Gone" not in text
    monkeypatch.setattr(operator_kit, "ecobuild", lambda args, timeout=120: {"ok": False})
    assert operator_kit.context() == ""
