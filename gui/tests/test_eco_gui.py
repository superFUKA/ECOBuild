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
        self.members = [{"login": "octocat", "role": "write", "invited": False}, {"login": "hubot", "role": "read", "invited": True}]

    def commands(self):
        text = {"type": "string"}
        return {
            "account show": {"description": "アカウント", "args": {"type": "object", "properties": {}, "required": []}, "weight": "read"},
            **{name: {"description": name, "args": {"type": "object", "properties": {}, "required": []}, "weight": "read"}
               for name in ("module show", "task list", "pipeline list", "ci show", "ci status")},
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
        self.calls.append((name, args))
        if name == "account show":
            return {"ok": True, "result": {"login": "superFUKA", "role": "admin"}}
        if name == "module members":
            return {"ok": True, "result": list(self.members)}
        if name == "module members remove":
            self.members = [m for m in self.members if m["login"] != args["user"]]
        if name == "module show":
            return {"ok": True, "result": {"name": "Calc", "type": "python", "private": True}}
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
    backend = EcobuildBackend(["ecobuild", "-C", "."])
    backend.ask = lambda argv: catalog
    specs = backend.commands()
    assert set(specs) == {"module members", "module members remove", "doctor", "build"}  # 今の型（python）のコマンドだけ足す
    assert specs["doctor"]["weight"] == "confirm"  # 「人がする」は、窓の前の人に確かめてから
    assert specs["module members remove"]["args"] == {"type": "object", "required": ["user"],
                                                      "properties": {"user": {"type": "string", "description": "外す人"}}}
    assert backend.command_line("module members remove", {"user": "octocat"}, ["yes"]) == [
        "ecobuild", "-C", ".", "module", "members", "remove", "--yes", "--json", "--", "octocat"]
    assert backend.command_line("build", {"targets": ["a", "b"], "clean": False}) == [
        "ecobuild", "-C", ".", "build", "--no-clean", "--json", "--", "a", "b"]


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
