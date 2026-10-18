"""GUIの操作（actions.py）：画面のボタンと、外の口（ecobuild gui・MCP）が同じ操作を通ること。"""

import io
import json
import re
import sys
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GUI))
import actions  # noqa: E402
import app as gui  # noqa: E402
import ecobuild_gui  # noqa: E402

STATIC = GUI / "static"


def test_the_buttons_use_the_actions():
    """画面のコードは、ecobuild のコマンド・GUIにしかない操作（開く・VS・窓）をサーバーに直接頼まない（common.js の
    操作の層だけが頼む）。ECO.action で呼ぶ名前は、すべて一覧にある。"""
    direct = re.compile(r"\bcall\('(cli|open|open-vs|open-file-vs|open-window)'")
    for path in STATIC.glob("*.js"):
        text = path.read_text(encoding="utf-8")
        if path.name != "common.js":
            assert not direct.search(text), f"{path.name}：{direct.search(text).group(0)}"
        for name in re.findall(r"ECO\.action\('([a-z-]+)'", text) + re.findall(r"\baction\('([a-z-]+)'", text):
            assert name in actions.ACTIONS, f"{path.name}：{name}"


def test_pages_in_a_window_are_that_window():
    """作業空間（モジュールの窓の中の iframe）の操作は、その窓の操作（窓の番号を使う。エージェントの操作に見えない）。"""
    text = (STATIC / "common.js").read_text(encoding="utf-8")
    assert "window.ECO = ECO;" in text and "window.top.ECO.windowId" in text


def test_check_names_and_params():
    assert actions.check("open", {"module": "M", "task": "12"}) == {"module": "M", "task": 12}
    assert actions.check("folder", {"dir": "C:/x", "reveal": "true"}) == {"dir": "C:/x", "reveal": True}
    for name, params in (("nosuch", {}), ("folder", {}), ("open", {"page": "nosuch"}), ("open", {"x": 1}),
                         ("run", {"args": "task list"})):
        with pytest.raises(ValueError):
            actions.check(name, params)


def make_app(tmp_path, script="import json; print(json.dumps({'ok': True, 'result': 1}))"):
    return gui.App(gui.Cli([sys.executable, "-c", script]), gui.Store(tmp_path / "gui.json"), "t", 1)


def test_run_tells_the_windows(tmp_path):
    """run：ecobuild を実行し、変える操作なら開いている画面に知らせる（誰が実行したか付き）。読むだけなら知らせない。"""
    app = make_app(tmp_path)
    app.see_window({"id": "w1", "kind": "module", "module": str(tmp_path)})
    assert app.action("run", {"args": ["task", "start", "12"]}, origin="")["ok"]
    assert app.action("run", {"args": ["status"]}, origin="w1")["ok"]
    assert app.action("run", {"args": ["task", "commit"]}, origin="w1")["ok"]
    ran = [e for e in app.events.items if e["type"] == "ran"]
    assert [(e["args"][1], e["by"]) for e in ran] == [("start", "agent"), ("commit", "window")]
    assert app.api("events", {"since": 0, "wait": 0})["events"][0]["args"] == ["task", "start", "12"]


def test_open_moves_a_window_or_opens_one(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(gui, "open_window", lambda url, size=None: opened.append(url))
    module = tmp_path / "M"
    (module / ".ecobuild").mkdir(parents=True)
    (module / ".ecobuild" / "ecobuild.toml").write_text('[module]\nname = "M"\n', encoding="utf-8")
    app = make_app(tmp_path)
    # no window: the server opens one (Edge), with where to go in the address
    assert app.action("open", {"module": str(module), "page": "tasks", "task": 7})["done"] == "opened"
    assert opened and "module.html?path=" in opened[0] and opened[0].endswith("#tasks/7")
    # the module's window is open: it moves there (an event for that window)
    app.see_window({"id": "w1", "kind": "module", "module": str(module)})
    assert app.action("open", {"module": str(module), "tab": "projects"})["window"] == "w1"
    navigate = [e for e in app.events.items if e["type"] == "navigate"][-1]
    assert navigate["target"] == "w1" and navigate["tab"] == "projects"
    # called by that window itself: it does it (apply)
    assert app.action("open", {"module": str(module), "page": "help"}, origin="w1") == {"apply": {"navigate": {"page": "help"}}}
    # the hub, from the hub: apply; folder from a window: the window opens it
    app.see_window({"id": "h1", "kind": "hub"})
    assert app.action("open", {}, origin="h1") == {"apply": {"navigate": {}}}
    assert app.action("folder", {"dir": str(module)}, origin="w1")["apply"]["open"]["dir"] == str(module)


def test_notify_windows_and_activity(tmp_path):
    app = make_app(tmp_path)
    app.see_window({"id": "w1", "kind": "hub", "page": "help"})
    assert app.action("notify", {"message": "終わりました"})["windows"] == 1
    listed = app.action("windows", {})
    assert listed[0]["id"] == "w1" and listed[0]["page"] == "help" and "seen" not in listed[0]
    assert [e["type"] for e in app.action("activity", {})] == ["notify"]
    with pytest.raises(gui.GuiError):
        app.action("nosuch", {})


def test_command_line_words():
    assert ecobuild_gui._parse("open", ["ECOSTL", "--page", "tasks", "--task", "3"]) == {"module": "ECOSTL", "page": "tasks", "task": "3"}
    assert ecobuild_gui._parse("folder", ["C:/x", "--reveal"]) == {"dir": "C:/x", "reveal": True}
    assert ecobuild_gui._parse("notify", ["hello"]) == {"message": "hello"}
    with pytest.raises(ecobuild_gui.Failure):
        ecobuild_gui._parse("open", ["--nosuch", "x"])


def test_ecobuild_commands_go_through_the_gui(monkeypatch, tmp_path, capsys):
    """ecobuild gui task start 12 → GUIの run（場所は -C か今のフォルダ）。結果は ecobuild と同じ形の JSON。"""
    called = []
    monkeypatch.setattr(ecobuild_gui, "act", lambda name, params: called.append((name, params)) or {"ok": True, "result": "done"})
    assert ecobuild_gui.main(["-C", str(tmp_path), "task", "start", "12", "--json"]) == 0
    assert called == [("run", {"args": ["task", "start", "12"], "dir": str(tmp_path.resolve())})]
    assert json.loads(capsys.readouterr().out)["result"] == "done"


def test_mcp_lists_and_calls_tools(monkeypatch, capsys):
    """MCP（標準入出力の JSON-RPC）：ツールは GUIの操作（ecobuild・gui_open 等）と ecobuild_commands。"""
    monkeypatch.setattr(ecobuild_gui, "act", lambda name, params: {"ok": True, "result": [name, params.get("args")]})
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
             {"jsonrpc": "2.0", "method": "notifications/initialized"},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
             {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "ecobuild", "arguments": {"args": ["task", "list"], "dir": "C:/M"}}},
             {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nosuch", "arguments": {}}}]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(json.dumps(x) for x in lines) + "\n"))
    assert ecobuild_gui.mcp() == 0
    answers = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [a["id"] for a in answers] == [1, 2, 3, 4]
    assert answers[0]["result"]["serverInfo"]["name"] == "ecobuild-gui"
    names = {t["name"] for t in answers[1]["result"]["tools"]}
    assert {"ecobuild", "gui_open", "gui_folder", "gui_vs", "gui_notify", "gui_windows", "gui_activity", "ecobuild_commands"} <= names
    assert answers[2]["result"]["isError"] is False and "task" in answers[2]["result"]["content"][0]["text"]
    assert answers[3]["result"]["isError"] is True


def test_the_command_is_put_next_to_ecobuild(tmp_path):
    ecobuild = tmp_path / ("ecobuild.exe" if sys.platform == "win32" else "ecobuild")
    ecobuild.write_text("", encoding="utf-8")
    made = gui.install_command([str(ecobuild)])
    assert made is not None and made.parent == tmp_path and "ecobuild_gui.py" in made.read_text(encoding="utf-8")
    assert gui.install_command([str(ecobuild)]) == made        # 同じなら書き直さない


def test_agents_go_to_the_electron_window(tmp_path):
    """エージェントの窓の操作：一覧は Electron の main が知らせた様子、ほかは main に頼む。窓がなければ失敗。"""
    app = make_app(tmp_path)
    with pytest.raises(gui.GuiError):
        app.action("agents", {})
    tabs = [{"num": 1, "name": "Calc #12", "dir": "C:/ECO/Calc", "state": "idle"}]
    app.see_window({"id": "agents-main", "kind": "agents", "tabs": tabs})
    assert app.action("agents", {}) == tabs
    assert app.action("agent-send", {"tab": "1", "text": "テストして"}) == {"done": "asked", "window": "agents-main"}
    event = app.events.items[-1]
    assert event["type"] == "agents" and event["op"] == "agent-send" and event["params"] == {"tab": 1, "text": "テストして"}
    with pytest.raises(gui.GuiError):
        app.action("agent-show", {"tab": 9})
    assert app.action("agent-open", {"dir": "C:/ECO/Calc"})["done"] == "asked"
