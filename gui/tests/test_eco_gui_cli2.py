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


