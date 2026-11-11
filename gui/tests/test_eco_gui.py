"""GUIFrameWork の上の GUI（eco_gui）：定義が通ること、画面がバックエンドのコマンドを正しく呼ぶこと。

GUIFrameWork が入っていない Python では飛ばす。ecobuild は呼ばない（偽のバックエンドで確かめる）。
"""

import importlib
import sys
from pathlib import Path

import pytest

pytest.importorskip("guiframework")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guiframework import create_app  # noqa: E402


class FakeEcobuild:
    """ecobuild の代わり。呼ばれたコマンドを覚える。"""

    def __init__(self):
        self.calls = []
        self.modules = []
        self.members = [{"login": "octocat", "role": "write", "invited": False}, {"login": "hubot", "role": "read", "invited": True}]

    def commands(self):
        text = {"type": "string"}
        specs = {}
        # どの試験でも全部の画面のつなぎが確かめられるよう、ほかの試験のファイルが足したコマンドも一覧に入れる
        for file in sorted(Path(__file__).parent.glob("test_eco_gui_*.py")):  # 足し忘れないよう、ファイルから集める
            importlib.import_module(file.stem)
        fakes = [fake() for fake in FakeEcobuild.__subclasses__() if not isinstance(self, fake)]
        for name, spec in [pair for fake in fakes for pair in fake._specs(text).items()] + list(self._specs(text).items()):
            known = specs.get(name)
            if known is not None:  # 同じコマンドをいくつかのファイルが書いている：引数は合わせたもの、ほかは後のもの
                spec = {**spec, "args": {**spec["args"], "properties": {**known["args"]["properties"], **spec["args"]["properties"]}}}
            specs[name] = spec
        for spec in specs.values():  # 本物と同じく、どのコマンドも module を受ける
            spec["args"]["properties"]["module"] = text
        return specs

    def _specs(self, text):
        return {
            "workspace list": {"description": "モジュールの一覧", "args": {"type": "object", "properties": {}, "required": []}, "weight": "read"},
            "account show": {"description": "アカウント", "args": {"type": "object", "properties": {}, "required": []}, "weight": "read"},
            **{name: {"description": name, "args": {"type": "object", "properties": {}, "required": []}, "weight": "read"}
               for name in ("module show", "task list", "pipeline list", "ci show", "ci status", "status", "files", "branch list")},
            "show": {"description": "コミット", "weight": "read", "args": {"type": "object", "required": [], "properties": {"commit": text}}},
            "doctor": {"description": "環境チェック", "weight": "read", "args": {"type": "object", "required": [], "properties": {}}},
            **{name: {"description": name, "weight": "change", "args": {"type": "object", "required": [key], "properties": {key: text}}}
               for name, key in (("workspace add", "path"), ("workspace forget", "path"), ("module clone", "repository"))},
            "module new": {"description": "モジュールを作ります", "weight": "change", "args": {"type": "object", "required": ["name"], "properties": {
                "name": text, "type": text}}},
            "file add": {"description": "ファイルを足します", "weight": "change", "args": {"type": "object", "required": [], "properties": {
                "paths": {"type": "array", "items": text}}}},
            "file remove": {"description": "ファイルを消します", "weight": "confirm", "args": {"type": "object", "required": [], "properties": {
                "paths": {"type": "array", "items": text}}}},
            "file move": {"description": "ファイルを動かします", "weight": "change", "args": {"type": "object", "required": ["source", "destination"], "properties": {
                "source": text, "destination": text}}},
            "task new": {"description": "タスクを作ります", "weight": "change", "args": {"type": "object", "required": ["title"], "properties": {"title": text}}},
            "task start": {"description": "タスクを始めます", "weight": "change", "args": {"type": "object", "required": ["issue"], "properties": {
                "issue": {"type": "integer"}, "name": text}}},
            "task close": {"description": "タスクを閉じます", "weight": "confirm", "args": {"type": "object", "required": ["issue"], "properties": {
                "issue": {"type": "integer"}}}},
            "branch create": {"description": "ブランチを作ります", "weight": "change", "args": {"type": "object", "required": ["name"], "properties": {
                "name": text, "base": text}}},
            "branch delete": {"description": "ブランチを消します", "weight": "confirm", "args": {"type": "object", "required": ["name"], "properties": {"name": text}}},
            **{name: {"description": name, "args": {"type": "object", "properties": {}, "required": []}, "weight": "change"} for name in ("stash", "stash pop")},
            "diff": {"description": "差分", "weight": "read", "args": {"type": "object", "required": [], "properties": {
                "paths": {"type": "array", "items": text}}}},
            "log": {"description": "履歴", "args": {"type": "object", "properties": {"count": {"type": "integer"}}, "required": []}, "weight": "read"},
            "task commit": {"description": "コミットします", "weight": "change", "args": {"type": "object", "required": [], "properties": {
                "paths": {"type": "array", "items": text}, "message": text}}},
            **{name: {"description": name, "args": {"type": "object", "properties": {}, "required": []}, "weight": weight}
               for name, weight in (("task push", "change"), ("sync", "change"), ("task submit", "confirm"),
                                    ("build", "change"), ("test", "change"), ("clean", "change"))},
            "ci run": {"description": "CI を流す", "args": {"type": "object", "properties": {}, "required": []}, "weight": "change"},
            **{f"pipeline {verb}": {"description": verb, "weight": "change",
                                    "args": {"type": "object", "properties": {"name": text, **({"steps": text} if verb == "add" else {})},
                                             "required": ["name"]}} for verb in ("add", "run", "remove")},
            "module members": {"description": "共同作業者", "args": {"type": "object", "properties": {}, "required": []}, "weight": "read"},
            "module members add": {"description": "招待します", "weight": "confirm",
                                   "args": {"type": "object", "properties": {"user": text, "role": text}, "required": ["user"]}},
            "module members remove": {"description": "外します", "weight": "confirm",
                                      "args": {"type": "object", "properties": {"user": text}, "required": ["user"]}},
        }

    def run(self, name, args, context, on_event):
        self.modules.append(args.get("module"))
        args = {key: value for key, value in args.items() if key != "module"}
        self.calls.append((name, args))
        if name == "workspace list":
            return {"ok": True, "result": {"modules": [{"path": "C:/work/Calc", "type": "python", "branch": "main"},
                                                       {"path": "C:/work/Game", "type": "cpp", "branch": "dev"}]}}
        if name == "account show":
            return {"ok": True, "result": {"login": "superFUKA", "role": "admin"}}
        if name == "module members":
            return {"ok": True, "result": list(self.members)}
        if name == "module members remove":
            self.members = [m for m in self.members if m["login"] != args["user"]]
        if name == "module show":
            return {"ok": True, "result": {"name": "Calc", "type": "python", "private": True, "workspaces": [
                {"name": "12", "path": "C:/work/Calc/.ecobuild/w/12", "branch": "task/12-login", "task": 12}]}}
        if name == "status":
            return {"ok": True, "result": {"branch": "task/12-login", "task": 12, "ahead": 1, "behind": 0,
                                           "staged": [], "unstaged": ["a.py", "b.py"], "untracked": ["new.txt"]}}
        if name == "build":
            for line in ("構成しています…\n", "ビルドしています…\n"):
                on_event({"event": "output", "message": line})
        if name == "doctor":
            return {"ok": True, "result": {"items": [{"id": "git", "name": "git", "ok": True, "detail": "2.55", "hint": ""}]}}
        if name == "branch list":
            return {"ok": True, "result": [{"name": "dev", "base": "main", "local": True, "remote": True, "merged": False}]}
        if name == "show":
            return {"ok": True, "result": f"commit {args['commit']}\n+中身"}
        if name == "files":
            return {"ok": True, "result": {"files": ["README.md", "src/app.py", "src/util/text.py"]}}
        if name == "diff":
            return {"ok": True, "result": f"diff --git a/{args['paths'][0]} b/{args['paths'][0]}\n+新しい行"}
        if name == "log":
            return {"ok": True, "result": [{"sha": "abc", "subject": "最初", "author": "octocat", "date": "2026-11-01"}]}
        if name == "task list":
            return {"ok": True, "result": [{"number": 12, "title": "ログイン画面", "stage": "in_progress", "assignees": ["octocat"]}]}
        if name == "pipeline list":
            return {"ok": True, "result": {"pipelines": [{"name": "check", "steps": ["build", "test"], "tests": []}]}}
        if name == "ci show":
            return {"ok": True, "result": {"path": ".github/workflows/ecobuild.yml", "exists": False}}
        if name == "ci status":
            return {"ok": True, "result": []}
        return {"ok": True, "result": None}

    def can(self, name, args):
        return True, ""

    def dry_run(self, name, args):
        return ""

    def cancel(self, run):
        return False


def test_ecobuild_catalog_is_converted_to_the_form_guiframework_reads():
    from eco_gui.backend import EcobuildBackend

    def option(param, name, flag=False, negative=None):
        return {"names": [name], "param": param, "help": param, "flag": flag, "type": "bool" if flag else "str",
                "negative": negative, "required": False, "multiple": False}

    catalog = {"ok": True, "result": {"type": "python", "commands": [
        {"name": "module", "path": "module", "summary": "モジュール", "help": "モジュール", "runnable": False, "commands": [
            {"name": "members", "path": "module members", "summary": "共同作業者", "help": "共同作業者", "runnable": True,
             "effect": "read", "arguments": [], "options": [option("json", "--json", True)], "commands": [
                 {"name": "remove", "path": "module members remove", "summary": "外します", "help": "外します", "runnable": True,
                  "effect": "confirm", "options": [option("yes", "--yes", True), option("json", "--json", True)],
                  "arguments": [{"name": "USER", "param": "user", "help": "外す人", "required": True, "multiple": False, "type": "str"}]}]}]},
        {"name": "doctor", "path": "doctor", "summary": "環境を確かめる", "help": "", "runnable": True, "effect": "human",
         "arguments": [], "options": []},
    ], "types": {"python": {"commands": [
        {"name": "build", "path": "build", "summary": "ビルド", "help": "", "runnable": True, "effect": "change",
         "arguments": [{"name": "TARGETS", "param": "targets", "help": "対象", "required": False, "multiple": True, "type": "str"}],
         "options": [option("clean", "--clean", True, "--no-clean")]}]}, "cpp": {"commands": [{"name": "vs", "path": "vs", "runnable": True, "effect": "change"}]}}}}
    backend = EcobuildBackend(["ecobuild"])
    backend.ask = lambda argv: catalog
    specs = backend.commands()
    assert set(specs) == {"module members", "module members remove", "doctor", "build", "vs"}  # どの型のコマンドも足す
    assert specs["doctor"]["weight"] == "confirm"  # 「人がする」は、窓の前の人に確かめてから
    assert specs["module members remove"]["args"]["required"] == ["user"]
    assert sorted(specs["module members remove"]["args"]["properties"]) == ["module", "user"]
    assert backend.command_line("module members remove", {"user": "octocat"}, ["yes"]) == [
        "ecobuild", "module", "members", "remove", "--yes", "--json", "--", "octocat"]
    assert backend.command_line("build", {"targets": ["a", "b"], "clean": False, "module": "C:/m"}) == [
        "ecobuild", "-C", "C:/m", "build", "--no-clean", "--json", "--", "a", "b"]


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=FakeEcobuild(), roles={"confirm": "confirm-box"})
    return app.relay(threaded=True)


def nodes(relay, window):
    return {node["id"]: node for node in relay.display.tree(window)["nodes"]}


def answer(relay, window, yes):
    import time
    for _ in range(200):
        overlays = relay.display.tree(window)["overlays"]
        if overlays:
            relay.input(window, overlays[0]["id"], "answered", {"yes": yes}, human=True)
            relay.idle()
            return overlays[0]
        time.sleep(0.01)
    raise AssertionError("確認が出ません")


def test_hub_opens_a_window_per_module_and_commands_run_in_that_module(relay):
    hub = relay.execute({"command": "open", "screen": "hub"})["window"]
    relay.idle()
    assert [row["path"] for row in nodes(relay, hub)["modules"]["props"]["rows"]] == ["C:/work/Calc", "C:/work/Game"]
    relay.input(hub, "modules", "action", {"id": "C:/work/Game", "action": "open"}, human=True)
    relay.idle()
    opened = [w for w in relay.display.windows() if w["screen"] == "overview"]
    assert [w["args"] for w in opened] == [{"module": "C:/work/Game"}]
    assert relay.backend.modules[-1] == "C:/work/Game"  # そのモジュールで読む
    relay.input(opened[0]["id"], "nav", "selected", {"id": "tasks"}, human=True)  # メニューで切り替えても、同じモジュール
    relay.idle()
    assert relay.display.tree(opened[0]["id"])["args"] == {"module": "C:/work/Game"} and relay.backend.modules[-1] == "C:/work/Game"
    relay.input(hub, "modules", "action", {"id": "C:/work/Calc", "action": "open"}, human=True)
    relay.idle()
    assert len(relay.display.windows()) == 3  # モジュールごとに窓


def test_the_module_argument_becomes_ecobuild_dash_c():
    from eco_gui.backend import EcobuildBackend

    backend = EcobuildBackend(["ecobuild"])
    backend.ask = lambda argv: {"ok": True, "result": {"type": None, "commands": [
        {"name": "status", "path": "status", "summary": "状態", "runnable": True, "effect": "read", "arguments": [],
         "options": [{"names": ["--fetch"], "param": "fetch", "flag": True, "type": "bool", "negative": "--no-fetch"}]}]}}
    assert "module" in backend.commands()["status"]["args"]["properties"]
    assert backend.command_line("status", {"module": "C:/work/Calc", "fetch": True}) == ["ecobuild", "-C", "C:/work/Calc", "status", "--fetch", "--json"]
    assert backend.command_line("status", {}) == ["ecobuild", "status", "--json"]


def test_workspace_commits_the_checked_files_with_the_same_command_a_person_types(relay):
    overview = relay.execute({"command": "open", "screen": "overview", "args": {"module": "C:/work/Calc"}})["window"]
    relay.idle()
    relay.input(overview, "spaces", "action", {"id": "C:/work/Calc/.ecobuild/w/12", "action": "open"}, human=True)
    relay.idle()
    window = next(w["id"] for w in relay.display.windows() if w["screen"] == "workspace")
    view = nodes(relay, window)
    assert view["state"]["props"]["data"]["branch"] == "task/12-login"
    assert view["changes"]["props"]["status"]["unstaged"] == ["a.py", "b.py"]
    assert relay.backend.calls.count(("status", {})) == 1  # 2つの部品へ出しても、status は1回
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"

    relay.input(window, "changes", "changed", {"paths": ["a.py", "new.txt"]}, human=True)
    relay.input(window, "commit_box", "changed", {"text": "ログインを直す"}, human=True)
    relay.idle()
    assert nodes(relay, window)["changes"]["props"]["checked"] == ["a.py", "new.txt"]
    relay.input(window, "commit_box", "commit", {}, human=True)
    relay.idle()
    assert ("task commit", {"paths": ["a.py", "new.txt"], "message": "ログインを直す"}) in relay.backend.calls
    assert relay.display.values(window)["paths"] is None and nodes(relay, window)["changes"]["props"]["checked"] == []
    relay.input(window, "tabs", "selected", {"tab": "submit"}, human=True)  # 「提出」のタブへ
    relay.input(window, "submit", "pressed", {}, human=True)  # 提出は、確かめてから
    assert answer(relay, window, True)["part"] == "confirm-box"
    assert ("task submit", {}) in relay.backend.calls


def test_build_output_is_shown_as_it_arrives(relay):
    window = relay.execute({"command": "open", "screen": "workspace", "args": {"module": "C:/work/Calc"}})["window"]
    relay.idle()
    relay.input(window, "toolbar", "action", {"name": "build"}, human=True)
    relay.idle()
    assert ("build", {}) in relay.backend.calls and relay.backend.modules[-1] == "C:/work/Calc"
    assert nodes(relay, window)["out"]["props"]["lines"] == ["構成しています…", "ビルドしています…"]
    relay.input(window, "toolbar", "action", {"name": "clean"}, human=True)
    relay.idle()
    assert nodes(relay, window)["out"]["props"]["lines"] == []  # 次の実行が始まると、前の出力は消える


def test_commands_of_every_module_type_are_listed_once():
    from eco_gui.backend import EcobuildBackend

    def node(path, effect="change"):
        return {"name": path.split()[-1], "path": path, "summary": path, "runnable": True, "effect": effect, "arguments": [], "options": []}

    backend = EcobuildBackend(["ecobuild"])
    backend.ask = lambda argv: {"ok": True, "result": {"type": None, "commands": [node("status", "read")], "types": {
        "cpp": {"commands": [node("build"), node("vs")]}, "python": {"commands": [node("build"), node("test")]}}}}
    assert sorted(backend.commands()) == ["build", "status", "test", "vs"]


def test_files_screen_shows_the_tree_and_the_diff_of_the_selected_file(relay):
    window = relay.execute({"command": "open", "screen": "files", "args": {"module": "C:/work/Calc"}})["window"]
    relay.idle()
    assert nodes(relay, window)["tree"]["props"]["paths"] == ["README.md", "src/app.py", "src/util/text.py"]
    assert not [call for call in relay.backend.calls if call[0] == "diff"]  # 選ぶまで、差分は読まない
    relay.input(window, "tree", "selected", {"path": "src/app.py"}, human=True)
    relay.idle()
    view = nodes(relay, window)
    assert view["tree"]["props"]["selected"] == "src/app.py"
    assert view["diff"]["props"]["text"].startswith("diff --git a/src/app.py") and ("diff", {"paths": ["src/app.py"]}) in relay.backend.calls


def test_task_rows_start_and_close_with_the_number_as_an_integer(relay):
    window = relay.execute({"command": "open", "screen": "tasks", "args": {"module": "C:/work/Calc"}})["window"]
    relay.idle()
    relay.input(window, "start_name", "changed", {"text": "ログイン画面"}, human=True)
    relay.input(window, "tasks", "action", {"id": "12", "action": "start"}, human=True)  # 表は ID を文字で出す
    relay.idle()
    assert ("task start", {"issue": 12, "name": "ログイン画面"}) in relay.backend.calls  # コマンドの型（数）で渡る
    relay.input(window, "tasks", "action", {"id": "12", "action": "close"}, human=True)
    answer(relay, window, True)  # 閉じるのは、確かめてから
    assert ("task close", {"issue": 12}) in relay.backend.calls
    relay.input(window, "new_title", "changed", {"text": "ログを残す"}, human=True)
    relay.idle()
    relay.input(window, "new", "pressed", {}, human=True)
    relay.idle()
    assert ("task new", {"title": "ログを残す"}) in relay.backend.calls


def test_branches_and_history_screens(relay):
    window = relay.execute({"command": "open", "screen": "branches", "args": {"module": "C:/work/Calc"}})["window"]
    relay.idle()
    assert nodes(relay, window)["tree"]["props"]["branches"][0]["name"] == "dev"
    relay.input(window, "detail", "action", {"action": "delete", "name": "dev"}, human=True)
    answer(relay, window, False)
    assert ("branch delete", {"name": "dev"}) not in relay.backend.calls
    relay.input(window, "nav", "selected", {"id": "history"}, human=True)
    relay.idle()
    assert nodes(relay, window)["log"]["props"]["rows"][0]["sha"] == "abc"
    relay.input(window, "log", "selected", {"sha": "abc"}, human=True)
    relay.idle()
    assert nodes(relay, window)["detail"]["props"]["text"].startswith("commit abc")


def test_files_screen_adds_moves_and_removes_files(relay):
    window = relay.execute({"command": "open", "screen": "files", "args": {"module": "C:/work/Calc"}})["window"]
    relay.idle()
    assert nodes(relay, window)["move"]["wrap"]["kind"] == "unavailable"  # まだ選んでいない
    relay.input(window, "new_path", "changed", {"text": "src/util.py"}, human=True)
    relay.idle()
    relay.input(window, "do_add", "pressed", {}, human=True)
    relay.idle()
    assert ("file add", {"paths": ["src/util.py"]}) in relay.backend.calls
    relay.input(window, "tree", "selected", {"path": "src/app.py"}, human=True)
    relay.input(window, "destination", "changed", {"text": "src/main.py"}, human=True)
    relay.idle()
    assert nodes(relay, window)["selected"]["props"]["text"] == "src/app.py"
    relay.input(window, "move", "pressed", {}, human=True)
    relay.idle()
    assert ("file move", {"source": "src/app.py", "destination": "src/main.py"}) in relay.backend.calls
    assert relay.display.values(window)["file"] is None  # 動かしたら、選択を空に
    relay.input(window, "tree", "selected", {"path": "README.md"}, human=True)
    relay.idle()
    relay.input(window, "remove", "pressed", {}, human=True)
    answer(relay, window, True)  # 消すのは、確かめてから
    assert ("file remove", {"paths": ["README.md"]}) in relay.backend.calls


def test_the_menu_switches_screens_in_the_same_window(relay):
    relay.verify()  # どの画面のつなぎも、バックエンドのコマンドと合っている
    window = relay.execute({"command": "open", "screen": "overview"})["window"]
    relay.idle()
    assert nodes(relay, window)["about"]["props"]["data"]["name"] == "Calc"
    assert nodes(relay, window)["nav"]["props"]["current"] == "overview"
    menu = [item["id"] for item in nodes(relay, window)["nav"]["props"]["items"]]
    assert set(menu) >= {"board", "schedule", "submissions", "agents", "settings", "container", "help"}
    known = ("files", "tasks", "branches", "history", "members", "pipelines", "ci", "overview")
    for screen in known:
        relay.input(window, "nav", "selected", {"id": screen}, human=True)
        relay.idle()
        tree = relay.display.tree(window)
        assert (tree["screen"], nodes(relay, window)["nav"]["props"]["current"]) == (screen, screen)
    assert [e["message"] for e in relay.display.events_after(0) if e["command"] == "notify"] == []
    for screen in [item for item in menu if item not in known]:  # ほかの項目も、同じ窓で開ける（中身は、それぞれの試験で）
        relay.input(window, "nav", "selected", {"id": screen}, human=True)
        relay.idle()
        assert relay.display.tree(window)["screen"] == screen
    assert [w["id"] for w in relay.display.windows()] == [window]  # 窓は増えない


def test_row_buttons_call_different_commands(relay):
    window = relay.execute({"command": "open", "screen": "pipelines"})["window"]
    relay.idle()
    assert nodes(relay, window)["list"]["props"]["data"]["pipelines"][0]["name"] == "check"
    relay.input(window, "list", "action", {"action": "run", "name": "check"}, human=True)
    relay.idle()
    assert ("pipeline run", {"name": "check"}) in relay.backend.calls
    assert ("pipeline remove", {"name": "check"}) not in relay.backend.calls  # 押したボタンのコマンドだけ
    relay.input(window, "list", "action", {"action": "remove", "name": "check", "used": ""}, human=True)  # 消すのは、入力の窓で確かめてから
    relay.idle()
    form = next(w["id"] for w in relay.display.windows() if w["screen"] == "mod-pipeline-remove")
    relay.input(form, "form", "submitted", {"values": {"place": "C:/work/Calc/.ecobuild/w/12"}}, human=True)
    relay.idle()
    assert ("pipeline remove", {"name": "check"}) in relay.backend.calls
    relay.input(window, "list", "action", {"action": "add"}, human=True)
    relay.idle()
    form = next(w["id"] for w in relay.display.windows() if w["screen"] == "mod-pipeline-edit")
    relay.input(form, "form", "submitted", {"values": {"place": "C:/work/Calc/.ecobuild/w/12", "name": "nightly", "steps": "build,test", "tests": ""}}, human=True)
    relay.idle()
    assert ("pipeline add", {"name": "nightly", "steps": "build,test"}) in relay.backend.calls


def test_members_screen_reads_and_runs_the_same_commands_a_person_types(relay):
    window = relay.execute({"command": "open", "screen": "members"})["window"]
    relay.idle()
    view = nodes(relay, window)
    assert view["nav"]["props"]["current"] == "members"
    assert view["members"]["props"]["account"]["login"] == "superFUKA"
    assert [row["login"] for row in view["members"]["props"]["members"]] == ["octocat", "hubot"]

    relay.input(window, "members", "action", {"action": "invite"}, human=True)  # 招待は、入力の窓で
    relay.idle()
    form = next(w["id"] for w in relay.display.windows() if w["screen"] == "mod-member-invite")
    relay.input(form, "form", "submitted", {"values": {"user": "newbie", "role": ""}}, human=True)
    assert answer(relay, form, True)["part"] == "confirm-box"  # 変える前に、窓の前の人に確かめる
    assert ("module members add", {"user": "newbie"}) in relay.backend.calls  # 役割（任意）は決めなくてよい

    relay.input(window, "members", "action", {"action": "invite"}, human=True)
    relay.idle()
    form = next(w["id"] for w in relay.display.windows() if w["screen"] == "mod-member-invite")
    relay.input(form, "form", "submitted", {"values": {"user": "newbie", "role": "admin"}}, human=True)
    answer(relay, form, True)
    assert ("module members add", {"user": "newbie", "role": "admin"}) in relay.backend.calls

    relay.input(window, "members", "action", {"action": "remove", "login": "octocat"}, human=True)
    answer(relay, window, False)
    assert ("module members remove", {"user": "octocat"}) not in relay.backend.calls
    relay.input(window, "members", "action", {"action": "remove", "login": "octocat"}, human=True)
    answer(relay, window, True)
    assert ("module members remove", {"user": "octocat"}) in relay.backend.calls
    assert [row["login"] for row in nodes(relay, window)["members"]["props"]["members"]] == ["hubot"]  # 変えたら読み直す
