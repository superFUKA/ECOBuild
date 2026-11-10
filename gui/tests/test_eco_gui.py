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
        specs = self._specs(text)
        for spec in specs.values():  # 本物と同じく、どのコマンドも module を受ける
            spec["args"]["properties"]["module"] = text
        return specs

    def _specs(self, text):
        return {
            "workspace list": {"description": "モジュールの一覧", "args": {"type": "object", "properties": {}, "required": []}, "weight": "read"},
            "account show": {"description": "アカウント", "args": {"type": "object", "properties": {}, "required": []}, "weight": "read"},
            **{name: {"description": name, "args": {"type": "object", "properties": {}, "required": []}, "weight": "read"}
               for name in ("module show", "task list", "pipeline list", "ci show", "ci status", "status")},
            "log": {"description": "履歴", "args": {"type": "object", "properties": {"count": {"type": "integer"}}, "required": []}, "weight": "read"},
            "task commit": {"description": "コミットします", "weight": "change", "args": {"type": "object", "required": [], "properties": {
                "paths": {"type": "array", "items": text}, "message": text}}},
            **{name: {"description": name, "args": {"type": "object", "properties": {}, "required": []}, "weight": weight}
               for name, weight in (("task push", "change"), ("sync", "change"), ("task submit", "confirm"))},
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
    assert set(specs) == {"module members", "module members remove", "doctor", "build"}  # 今の型（python）のコマンドだけ足す
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
    relay.input(window, "message", "changed", {"text": "ログインを直す"}, human=True)
    relay.idle()
    assert nodes(relay, window)["changes"]["props"]["checked"] == ["a.py", "new.txt"]
    relay.input(window, "do_commit", "pressed", {}, human=True)
    relay.idle()
    assert ("task commit", {"paths": ["a.py", "new.txt"], "message": "ログインを直す"}) in relay.backend.calls
    assert relay.display.values(window)["paths"] == [] and nodes(relay, window)["changes"]["props"]["checked"] == []
    relay.input(window, "submit", "pressed", {}, human=True)  # 提出は、確かめてから
    assert answer(relay, window, True)["part"] == "confirm-box"
    assert ("task submit", {}) in relay.backend.calls


def test_the_menu_switches_screens_in_the_same_window(relay):
    relay.verify()  # どの画面のつなぎも、バックエンドのコマンドと合っている
    window = relay.execute({"command": "open", "screen": "overview"})["window"]
    relay.idle()
    assert nodes(relay, window)["info"]["props"]["data"]["name"] == "Calc"
    assert nodes(relay, window)["nav"]["props"]["current"] == "overview"
    for screen in ("tasks", "members", "pipelines", "ci", "overview"):
        relay.input(window, "nav", "selected", {"id": screen}, human=True)
        relay.idle()
        tree = relay.display.tree(window)
        assert (tree["screen"], nodes(relay, window)["nav"]["props"]["current"]) == (screen, screen)
    assert [w["id"] for w in relay.display.windows()] == [window]  # 窓は増えない
    assert [e["message"] for e in relay.display.events_after(0) if e["command"] == "notify"] == []


def test_row_buttons_call_different_commands(relay):
    window = relay.execute({"command": "open", "screen": "pipelines"})["window"]
    relay.idle()
    assert nodes(relay, window)["list"]["props"]["rows"][0]["name"] == "check"
    relay.input(window, "list", "action", {"id": "check", "action": "run"}, human=True)
    relay.idle()
    assert ("pipeline run", {"name": "check"}) in relay.backend.calls
    assert ("pipeline remove", {"name": "check"}) not in relay.backend.calls  # 押したボタンのコマンドだけ
    relay.input(window, "list", "action", {"id": "check", "action": "remove"}, human=True)
    relay.idle()
    assert ("pipeline remove", {"name": "check"}) in relay.backend.calls
    relay.input(window, "name", "changed", {"text": "nightly"}, human=True)
    relay.input(window, "steps", "changed", {"text": "build,test"}, human=True)
    relay.idle()
    relay.input(window, "add", "pressed", {}, human=True)
    relay.idle()
    assert ("pipeline add", {"name": "nightly", "steps": "build,test"}) in relay.backend.calls


def test_members_screen_reads_and_runs_the_same_commands_a_person_types(relay):
    window = relay.execute({"command": "open", "screen": "members"})["window"]
    relay.idle()
    view = nodes(relay, window)
    assert view["nav"]["props"]["current"] == "members"
    assert view["me"]["props"]["text"] == "superFUKA"
    assert [row["login"] for row in view["members"]["props"]["rows"]] == ["octocat", "hubot"]
    assert view["add"]["wrap"]["kind"] == "unavailable"  # だれを招待するか、まだ決まっていない

    relay.input(window, "user", "changed", {"text": "newbie"}, human=True)
    relay.idle()
    assert nodes(relay, window)["add"]["wrap"] is None  # 役割（任意）は決めなくてよい
    relay.input(window, "add", "pressed", {}, human=True)
    assert answer(relay, window, True)["part"] == "confirm-box"  # 変える前に、窓の前の人に確かめる
    assert ("module members add", {"user": "newbie"}) in relay.backend.calls

    relay.input(window, "role", "changed", {"value": "admin"}, human=True)
    relay.idle()
    relay.input(window, "add", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("module members add", {"user": "newbie", "role": "admin"}) in relay.backend.calls

    relay.input(window, "members", "action", {"id": "octocat", "action": "remove"}, human=True)
    answer(relay, window, False)  # いいえ：実行しない
    assert ("module members remove", {"user": "octocat"}) not in relay.backend.calls
    relay.input(window, "members", "action", {"id": "octocat", "action": "remove"}, human=True)
    answer(relay, window, True)
    assert ("module members remove", {"user": "octocat"}) in relay.backend.calls
    assert [row["login"] for row in nodes(relay, window)["members"]["props"]["rows"]] == ["hubot"]  # 変えたら読み直す
