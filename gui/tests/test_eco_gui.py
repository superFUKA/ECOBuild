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
        return {"ok": True, "result": None}

    def can(self, name, args):
        return True, ""

    def dry_run(self, name, args):
        return ""

    def cancel(self, run):
        return False


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


def test_members_screen_reads_and_runs_the_same_commands_a_person_types(relay):
    window = relay.execute({"command": "open", "screen": "members"})["window"]
    relay.idle()
    view = nodes(relay, window)
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
