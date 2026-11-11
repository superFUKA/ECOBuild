"""新しい GUI（eco_gui）への道（next_gui.py・ecobuild_gui.target）：どちらの GUI に頼むかの決まりと、GUIの操作を
新しい GUI の表示の CLI（open・windows・tree・emit・notify …）へ直すこと。オペレーターの道具（MCP）と一式。

エージェント（claude）も ecobuild も動かさない。最後の1つだけ、本物の中継地点（偽のバックエンド）に表示の CLI で頼む。
"""

import io
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import actions  # noqa: E402
import ecobuild_gui  # noqa: E402
import next_gui  # noqa: E402
import operator_kit  # noqa: E402


@pytest.fixture
def undecided(monkeypatch):
    """頼み先を決めていない（動いている GUI で決まる）。"""
    monkeypatch.delenv("ECOBUILD_GUI_TARGET")
    monkeypatch.setattr(ecobuild_gui, "_decided", [])


@pytest.fixture
def sent(monkeypatch):
    """新しい GUI に頼む。表示の CLI は呼ばず、送った命令を覚える。"""
    calls = []
    answers = {"open": {"window": "w1"}, "windows": {"windows": [
        {"id": "w0", "screen": "hub", "args": {}, "title": "ECOBuild Hub", "looking": False, "parent": None},
        {"id": "w1", "screen": "tasks", "args": {"module": "C:/work/Calc"}, "title": "Calc — ECOBuild", "looking": True, "parent": None}]},
        "describe": {"screens": [{"name": "tasks", "description": "タスク", "args": {"module": "."}}], "parts": []},
        "tree": {"window": "w1", "nodes": []}}

    def display(command, *words, options=(), by=None, timeout=120):
        calls.append((command, words, options, by))
        return answers.get(command)

    monkeypatch.setenv("ECOBUILD_GUI_TARGET", "next")
    monkeypatch.setattr(next_gui, "display", display)
    return calls


def test_which_gui_is_asked(undecided, monkeypatch):
    """決まり：はっきり決めてあればそれ／新しい GUI の中から頼まれたら新しい GUI／ほかは動いている方（両方なら今までの GUI）／
    どちらも動いていなければ今までの GUI。"""
    alive = {"classic": False, "next": False}
    monkeypatch.setattr(ecobuild_gui, "_alive", lambda state: alive["classic"])
    monkeypatch.setattr(next_gui, "running", lambda: alive["next"])

    def asked(classic, new):
        alive.update(classic=classic, next=new)
        ecobuild_gui._decided.clear()
        return ecobuild_gui.target()

    assert asked(False, False) == "classic" and asked(True, False) == "classic"
    assert asked(False, True) == "next"
    assert asked(True, True) == "classic"                      # 両方動いていれば、今までどおり
    assert ecobuild_gui.table() is actions.ACTIONS
    monkeypatch.setenv("GUIFRAMEWORK_WINDOW", "w1")            # 新しい GUI の画面が実行したコマンドの中
    assert asked(True, True) == "next" and ecobuild_gui.table() is next_gui.ACTIONS
    monkeypatch.setenv("ECOBUILD_GUI_TARGET", "classic")       # はっきり決めてあれば、それ
    assert asked(False, True) == "classic"
    monkeypatch.setenv("ECOBUILD_GUI_TARGET", "next")
    monkeypatch.delenv("GUIFRAMEWORK_WINDOW")
    assert asked(True, False) == "next"


def test_the_running_gui_is_asked_once_per_request(undecided, monkeypatch):
    asked = []
    monkeypatch.setattr(ecobuild_gui, "_alive", lambda state: False)
    monkeypatch.setattr(next_gui, "running", lambda: asked.append(1) or True)
    assert [ecobuild_gui.target(), ecobuild_gui.target()] == ["next", "next"] and len(asked) == 1


def test_actions_become_display_commands(sent, tmp_path, monkeypatch, capsys):
    """open・windows・tree・emit・notify・screens は、表示の CLI の命令になる（人が窓でするのと同じ道）。"""
    module = tmp_path / "Calc"
    module.mkdir()
    where = module.resolve().as_posix()
    assert ecobuild_gui.act("open", {}) == {"gui": "next", "screen": "hub", "window": "w1"}
    assert ecobuild_gui.act("open", {"module": str(module)})["screen"] == "overview"
    assert ecobuild_gui.act("open", {"module": str(module), "page": "workspace"})["screen"] == "frame-workspaces"
    opened = ecobuild_gui.act("open", {"module": str(module), "page": "tasks", "screen": "submissions", "args": ["all=true"]})
    assert opened == {"gui": "next", "screen": "submissions", "module": where, "window": "w1"}
    assert [(c[0], c[1]) for c in sent] == [("open", ("hub",)), ("open", ("overview", f"module={where}")),
                                            ("open", ("frame-workspaces", f"module={where}")),
                                            ("open", ("submissions", f"module={where}", "all=true"))]
    sent.clear()
    windows = ecobuild_gui.act("windows", {})
    assert [w.get("module") for w in windows] == [None, "C:/work/Calc"] and windows[1]["looking"] is True
    assert ecobuild_gui.act("tree", {"window": "w1"}) == {"window": "w1", "nodes": []}
    assert ecobuild_gui.act("screens", {})[0]["name"] == "tasks"
    ecobuild_gui.act("emit", {"target": "w1/list", "output": "selected", "payload": ["number=12"]})
    assert ecobuild_gui.act("notify", {"message": "-x", "kind": "bad"}) == {"gui": "next"}
    assert [(c[0], c[1], c[2]) for c in sent] == [
        ("windows", (), ()), ("tree", (), ("--window", "w1")), ("describe", (), ()),
        ("emit", ("w1/list", "selected", "number=12"), ()), ("notify", ("-x",), ("--level", "error"))]
    # コマンドラインからも同じ（並びの引数は --名前 を何度でも）
    sent.clear()
    assert ecobuild_gui.main(["emit", "w1/go", "pressed", "--payload", "a=1", "--payload", "b=2", "--json"]) == 0
    assert ecobuild_gui.main(["tree", "--json"]) == 0
    assert [(c[0], c[1]) for c in sent] == [("emit", ("w1/go", "pressed", "a=1", "b=2")), ("tree", ())]
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["result"] == {"window": "w1", "nodes": []}


def test_a_module_is_found_by_its_name(sent, monkeypatch):
    listed = {"ok": True, "result": {"modules": [{"path": "C:\\work\\Calc", "repository": "acme/Calc"},
                                                 {"path": "C:/work/Game-2", "repository": "acme/Game"}]}}
    monkeypatch.setattr(ecobuild_gui, "_ecobuild", lambda args, directory=None, stdin=None: listed)
    assert ecobuild_gui.act("open", {"module": "calc", "page": "tasks"})["module"] == "C:/work/Calc"
    assert ecobuild_gui.act("open", {"module": "Game-2"})["module"] == "C:/work/Game-2"
    with pytest.raises(ecobuild_gui.Failure) as missing:
        ecobuild_gui.act("open", {"module": "Nowhere"})
    assert missing.value.code == "not_found"


def test_what_the_new_gui_does_not_have_is_told(sent, capsys):
    """エージェントの窓（タブ）の操作は今までの GUI だけ：ない理由と代わりを答える。誤った引数は使い方の誤り。"""
    assert ecobuild_gui.main(["agents", "--json"]) == 1
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "not_supported" and "agent list" in error["hint"]
    assert ecobuild_gui.main(["operator", "--state", "show", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "not_supported"
    with pytest.raises(ecobuild_gui.Failure) as wrong:
        ecobuild_gui.act("open", {"task": 3})          # 今までの GUI の引数（新しい GUI では、開いた後に案内する）
    assert wrong.value.code == "usage_error" and sent == []


def test_a_gui_that_is_not_running_is_an_error(monkeypatch, capsys):
    monkeypatch.setenv("ECOBUILD_GUI_TARGET", "next")

    def display(command, *words, **more):
        raise next_gui.Refused("no_display", "中継地点が動いていません", "serve で起こします")

    monkeypatch.setattr(next_gui, "display", display)
    assert ecobuild_gui.main(["windows", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "no_display"
    monkeypatch.setattr(next_gui, "python", lambda: None)
    assert next_gui.running() is False


def test_run_goes_straight_to_ecobuild_and_asks_the_windows_to_reread(sent, monkeypatch, tmp_path, capsys):
    ran = []
    monkeypatch.setattr(ecobuild_gui, "_ecobuild", lambda args, directory=None, stdin=None: ran.append((args, directory)) or {"ok": True, "result": 1})
    monkeypatch.chdir(tmp_path)
    assert ecobuild_gui.main(["task", "start", "12", "--json"]) == 0
    assert ran == [(["task", "start", "12"], str(Path.cwd()))] and [c[0] for c in sent] == ["refresh"]


def test_the_operator_tools_in_the_new_gui(sent, monkeypatch, capsys):
    """オペレーターの道具（新しい GUI）：画面を開く・窓と今の表示を読む。入力を出す emit・何でも実行できる ecobuild はない。"""
    monkeypatch.setattr(operator_kit, "catalog", lambda where=None: {"commands": [
        {"path": "task", "commands": [{"path": "task list", "runnable": True, "effect": "read", "summary": ""},
                                      {"path": "task start", "runnable": True, "effect": "change", "summary": ""}]}], "types": {}})
    ran = []
    monkeypatch.setattr(ecobuild_gui, "_ecobuild", lambda args, directory=None, stdin=None: ran.append((args, directory)) or {"ok": True, "result": []})
    call = lambda ident, name, arguments: {"jsonrpc": "2.0", "id": ident, "method": "tools/call", "params": {"name": name, "arguments": arguments}}  # noqa: E731
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
             call(2, "gui_tree", {}), call(3, "gui_emit", {"target": "w1/go", "output": "pressed"}),
             call(4, "ecobuild_read", {"args": ["task", "list"], "dir": "C:/M"}), call(5, "ecobuild_read", {"args": ["task", "start", "1"]}),
             call(6, "gui_agent-open", {"dir": "C:/M"}), call(7, "gui_open", {"screen": "operator"})]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(json.dumps(x) for x in lines) + "\n"))
    assert ecobuild_gui.mcp(operator=True) == 0
    answers = {a["id"]: a["result"] for a in map(json.loads, capsys.readouterr().out.splitlines())}
    names = {t["name"] for t in answers[1]["tools"]}
    assert names == {"gui_open", "gui_screens", "gui_windows", "gui_tree", "gui_folder", "gui_vs", "gui_notify",
                     "ecobuild_commands", "ecobuild_read"}
    assert answers[2]["isError"] is False and answers[3]["isError"] and answers[5]["isError"]
    assert answers[4]["isError"] is False and ran == [(["task", "list"], "C:/M")]       # 読むだけ：窓に読み直しを頼まない
    assert answers[6]["isError"] and "今までの GUI だけ" in answers[6]["content"][0]["text"]
    assert answers[7]["isError"] is False
    assert [(c[0], c[1], c[3]) for c in sent] == [("tree", (), "オペレーター"), ("open", ("operator",), "オペレーター")]
    # ふつうの MCP（エージェント用）には、入力を出す emit もある
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(lines[0]) + "\n"))
    assert ecobuild_gui.mcp() == 0
    assert {"gui_emit", "ecobuild", "gui_tree"} <= {t["name"] for t in json.loads(capsys.readouterr().out)["result"]["tools"]}


def test_the_kit_for_the_new_gui(tmp_path, monkeypatch):
    """一式（新しい GUI）：指示は新しい GUI の操作で、MCP の設定は頼み先を固定した別のファイル（今までの GUI の分は変えない）。"""
    monkeypatch.setenv("ECOBUILD_GUI_HOME", str(tmp_path / "gui"))
    monkeypatch.setattr(operator_kit, "catalog", lambda where=None: {"commands": [], "types": {}})
    monkeypatch.setattr(operator_kit, "style", lambda: "")
    folder = operator_kit.prepare(gui="next")
    text = (folder / "CLAUDE.md").read_text(encoding="utf-8")
    assert "## この GUI での操作（新しい GUI）" in text and "gui_tree" in text and "gui_screens" in text
    assert "gui_agent-open" not in text and "gui_emit" not in text and "gui_agents" not in text
    assert "gui_open --module C:/ECO/ECOSTL --page tasks" in text       # どちらの GUI でも同じ言い方の例は残る
    server = json.loads((folder / "mcp-next.json").read_text(encoding="utf-8"))["mcpServers"]["ecobuild-gui"]
    assert server["env"] == {"ECOBUILD_GUI_TARGET": "next"} and server["args"][-2:] == ["mcp", "--operator"]
    assert not (folder / "mcp.json").exists()
    monkeypatch.setattr(operator_kit.shutil, "which", lambda name: "C:/bin/claude.exe")
    args = operator_kit._command(("claude",), "next")
    assert args[args.index("--mcp-config") + 1].endswith("mcp-next.json")
    operator_kit.prepare()                                                # 今までの GUI：今までどおり
    assert "env" not in json.loads((folder / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["ecobuild-gui"]
    text = (folder / "CLAUDE.md").read_text(encoding="utf-8")
    assert "新しい GUI" not in text and "gui_agent-open" in text


def test_asking_from_the_new_gui_gives_the_operator_the_new_gui(tmp_path, monkeypatch, capsys):
    """新しい GUI の画面から話しかけた（GUIFRAMEWORK_WINDOW がある）：オペレーターの GUI の操作は、新しい GUI に頼む。"""
    monkeypatch.delenv("ECOBUILD_GUI_TARGET")
    monkeypatch.setenv("GUIFRAMEWORK_WINDOW", "w1")
    asked = []
    reply = {"session": "s1", "text": "はい", "ok": True, "actions": []}
    monkeypatch.setattr(operator_kit, "converse", lambda text, **more: asked.append(more.get("gui")) or reply)
    monkeypatch.setattr(operator_kit, "ask", lambda text, **more: asked.append(more.get("gui")) or reply)
    assert ecobuild_gui.main(["ask", "--continue", "開いて", "--json"]) == 0 and ecobuild_gui.main(["ask", "開いて", "--json"]) == 0
    assert asked == ["next", "next"]


def test_the_help_document_is_quick_and_the_same_for_the_catalog(sent, monkeypatch, capsys):
    """--help --json（ecobuild の一覧が読む）は、動いている GUI を調べない。commands は頼み先によらず同じ。"""
    monkeypatch.setattr(next_gui, "running", lambda: pytest.fail("動いているかを調べた"))
    assert ecobuild_gui.main(["--help", "--json"]) == 0
    document = json.loads(capsys.readouterr().out)["result"]
    assert document["commands"] == ecobuild_gui.COMMANDS and {a["name"] for a in document["actions"]} == set(next_gui.ACTIONS)
    monkeypatch.setenv("ECOBUILD_GUI_TARGET", "classic")
    assert ecobuild_gui.main(["--help", "--json"]) == 0
    document = json.loads(capsys.readouterr().out)["result"]
    assert document["commands"] == ecobuild_gui.COMMANDS and {a["name"] for a in document["actions"]} == set(actions.ACTIONS)


def test_the_display_cli_of_a_running_relay(tmp_path, monkeypatch):
    """本物の中継地点（偽のバックエンド）に、表示の CLI で頼む：開く・窓を読む・表示を読む・入力を出す・知らせる。"""
    pytest.importorskip("guiframework")
    import importlib

    from guiframework import create_app

    from test_eco_gui_hub import FakeHub

    monkeypatch.setenv("GUIFRAMEWORK_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("GUIFRAMEWORK_NO_WINDOW", "1")
    monkeypatch.setenv("ECOBUILD_GUI_TARGET", "next")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(p for p in sys.path if p))     # 表示の CLI も、同じ GUIFrameWork で
    backend = FakeHub()
    server = create_app(importlib.import_module("eco_gui"), name="ecobuild-gui-next", backend=backend,
                        roles={"confirm": "confirm-box"}).server(opener=None)
    server.start()
    try:
        assert next_gui.running()
        opened = ecobuild_gui.act("open", {"screen": "operator"})
        assert opened["screen"] == "operator" and opened["window"]
        windows = ecobuild_gui.act("windows", {})
        assert [(w["screen"], w["looking"]) for w in windows] == [("operator", True)]
        server.relay.idle()
        tree = ecobuild_gui.act("tree", {})
        chat = next(n for n in tree["nodes"] if n["id"] == "chat")
        assert tree["screen"] == "operator" and chat["props"]["conversation"]["state"] == "idle"
        ecobuild_gui.act("emit", {"target": f"{opened['window']}/input", "output": "sent", "payload": ["text=タスクを見せて"]})
        server.relay.idle()
        assert ("gui ask", {"text": "タスクを見せて", "continue": True}) in backend.calls
        assert ecobuild_gui.act("notify", {"message": "見てください", "kind": "ok"}) == {"gui": "next"}
        assert "operator" in {s["name"] for s in ecobuild_gui.act("screens", {})}
    finally:
        server.shutdown()
    assert next_gui.running() is False
