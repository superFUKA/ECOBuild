"""eco_gui の、CLI に足した読むコマンドを使う所：ヘルプのコマンドの一覧（help）・退避を選んで戻す・捨てる（stash pop・drop <番号>）・
試験を一覧から選ぶ（tests）。

ecobuild は呼ばない（偽のバックエンドで確かめる。偽のバックエンドは、画面ごとの試験のファイルのものを使う）。
"""

import importlib

import pytest

pytest.importorskip("guiframework")

from guiframework import create_app  # noqa: E402

from test_eco_gui import answer, nodes  # noqa: E402
from test_eco_gui_agents import FakeAgents  # noqa: E402
from test_eco_gui_polish import PolishEcobuild, last, notices, opened, press  # noqa: E402


def _relay(backend):
    app = create_app(importlib.import_module("eco_gui"), backend=backend, roles={"confirm": "confirm-box"})
    relay = app.relay(threaded=True)
    relay.verify()  # どの画面のつなぎも、バックエンドのコマンドと合っている
    return relay


@pytest.fixture
def relay():
    return _relay(PolishEcobuild())


def test_help_reads_the_commands_once_with_the_help_command():
    relay = _relay(FakeAgents())
    window = relay.execute({"command": "open", "screen": "help-guide"})["window"]
    relay.idle()
    view = nodes(relay, window)
    assert view["guide"]["part"] == "cfg-help"
    assert relay.backend.calls == [("help", {})] and relay.backend.modules == [None]  # モジュールの外：-C なしで読む
    catalog = view["guide"]["props"]["catalog"]
    assert catalog["commands"][0]["path"] == "status" and catalog["types"]["python"]["commands"][0]["path"] == "tests"
    assert view["guide"]["props"]["first"] == "task start" and view["guide"]["props"]["type_labels"]["cpp"] == "C++"
    assert notices(relay) == []


def test_command_list_part_declares_no_output_and_has_every_state_sample():
    """コマンドの一覧の部品：探す・絞る・選ぶは部品の中（出力なし＝何も実行しない）。読み込み中・誤りの見本がある。"""
    app = create_app(importlib.import_module("eco_gui"), backend=PolishEcobuild(), roles={"confirm": "confirm-box"})
    parts = {part["name"]: part for part in app.describe()["parts"]}
    assert parts["command-list"]["outputs"] in ({}, [])
    assert set(parts["pick-list"]["outputs"]) == {"selected"} and set(parts["check-list"]["outputs"]) == {"changed"}


def test_stashes_screen_pops_and_drops_the_selected_one(relay):
    relay.backend.stashes = ["On task/12-login: 3つ目", "On task/12-login: 2つ目", "On task/12-login: 1つ目"]
    window = opened(relay, "stashes")
    assert nodes(relay, window)["list"]["props"]["items"] == relay.backend.stashes
    assert nodes(relay, window)["list"]["props"]["selected"] is None
    press(relay, window, "list", "selected", index=1)
    assert nodes(relay, window)["list"]["props"]["selected"] == 1
    press(relay, window, "pop")
    assert last(relay) == ("stash pop", {"index": 1}) and relay.backend.modules[-1] == "C:/work/Calc"
    view = nodes(relay, window)["list"]["props"]
    assert view["items"] == ["On task/12-login: 3つ目", "On task/12-login: 1つ目"] and view["selected"] is None  # 番号がずれるので、選択は外す
    press(relay, window, "list", "selected", index=0)  # 先頭（番号 0）も、選べば番号を渡す
    relay.input(window, "drop", "pressed", {}, human=True)
    assert answer(relay, window, True)["part"] == "confirm-box"  # 捨てるのは、確かめてから
    assert last(relay) == ("stash drop", {"index": 0})
    assert nodes(relay, window)["list"]["props"]["items"] == ["On task/12-login: 1つ目"]
    press(relay, window, "pop")  # 選ばなければ、番号を渡さない（このブランチで最後に退避したもの）
    assert last(relay) == ("stash pop", {})
    assert notices(relay) == []


def test_stashes_screen_keeps_the_selection_when_dropping_is_declined(relay):
    window = opened(relay, "stashes")
    press(relay, window, "list", "selected", index=1)
    relay.input(window, "drop", "pressed", {}, human=True)
    answer(relay, window, False)
    assert ("stash drop", {"index": 1}) not in relay.backend.calls and len(relay.backend.stashes) == 2
    assert nodes(relay, window)["list"]["props"]["selected"] == 1


def test_build_screen_lists_the_tests_and_runs_the_checked_ones(relay):
    window = opened(relay, "build")
    assert nodes(relay, window)["tests"]["props"]["rows"] == [] and ("tests", {}) not in relay.backend.calls  # 開いただけでは読まない
    press(relay, window, "tests_load")
    view = nodes(relay, window)
    assert [row["name"] for row in view["tests"]["props"]["rows"]] == [
        "tests/test_app.py::test_add", "tests/test_app.py::test_sub", "tests/test_login.py::test_login"]
    assert relay.backend.calls[-1] == ("tests", {}) and relay.backend.modules[-1] == "C:/work/Calc"  # 読むコマンド：ほかの読み直しは起きない
    press(relay, window, "test_checked")  # まだ選んでいない：試験を渡さない（＝全部を流す）
    assert last(relay) == ("test", {})
    press(relay, window, "tests", "changed", values=["tests/test_app.py::test_sub", "tests/test_login.py::test_login"])
    view = nodes(relay, window)
    assert view["tests"]["props"]["checked"] == ["tests/test_app.py::test_sub", "tests/test_login.py::test_login"]
    press(relay, window, "configuration", "changed", value="Release")
    press(relay, window, "test_checked")
    assert last(relay) == ("test", {"tests": ["tests/test_app.py::test_sub", "tests/test_login.py::test_login"], "configuration": "Release"})
    assert nodes(relay, window)["out"]["props"]["lines"] == ["2 passed"]
    press(relay, window, "tests", "changed", values=[])  # 全部外したら、試験を渡さない（＝全部を流す）
    press(relay, window, "test_checked")
    assert last(relay) == ("test", {"tests": [], "configuration": "Release"})
    assert notices(relay) == []
