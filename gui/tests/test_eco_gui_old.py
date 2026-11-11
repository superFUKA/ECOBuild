"""eco_gui の、今の GUI と同じ表示に戻した画面：ブランチ同士の取り込み・C++（Project・依存先・テンプレート）・ビルドと試験・退避・注釈履歴。

画面が、人が打つのと同じコマンドを正しい引数で呼ぶこと。GUIFrameWork が入っていない Python では飛ばす。
ecobuild は呼ばない（偽のバックエンドで確かめる）。
"""

import importlib

import pytest

pytest.importorskip("guiframework")

from guiframework import create_app  # noqa: E402
from test_eco_gui import answer, nodes  # noqa: E402
from test_eco_gui_polish import PolishEcobuild, spec  # noqa: E402
from test_eco_gui_review import FakeReview  # noqa: E402

CALC, GAME = "C:/work/Calc", "C:/work/Game"  # Python のモジュール・C++ のモジュール


class OldEcobuild(PolishEcobuild):
    """戻した画面が読む・呼ぶものを足した、ecobuild の代わり（下見は、提出・取り込みの試験のものと同じ）。"""

    def __init__(self):
        super().__init__()
        self.plans = []  # 下見を読んだコマンド
        self.previews = []

    def _specs(self, text):
        return {**super()._specs(text)}

    def run(self, name, args, context, on_event):
        result = super().run(name, args, context, on_event)
        given = {key: value for key, value in args.items() if key != "module"}
        if name == "account show":
            return {"ok": True, "result": {"login": "superFUKA", "role": "admin", "admin": True, "default_base": "main"}}
        if name == "branch list":
            return {"ok": True, "result": [
                {"name": "main", "base": None, "local": True, "remote": True, "is_task_branch": False},
                {"name": "dev", "base": "main", "local": True, "remote": True, "is_task_branch": False},
                {"name": "release", "base": "main", "local": True, "remote": True, "is_task_branch": False},
                {"name": "task/12-login", "base": "dev", "local": True, "remote": True, "is_task_branch": True}]}
        if name == "branch resolve":
            return {"ok": True, "result": {"task": 31, "workspace": "C:/work/Calc/.ecobuild/w/31", "conflicts": ["src/app.py"], **given}}
        return result

    preview = FakeReview.preview
    dry_run = FakeReview.dry_run


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=OldEcobuild(), roles={"confirm": "confirm-box"})
    relay = app.relay(threaded=True)
    relay.verify()  # どの画面のつなぎも、バックエンドのコマンドと合っている
    return relay


def opened(relay, screen, module=CALC, **args):
    window = relay.execute({"command": "open", "screen": screen, "args": {"module": module, **args}})["window"]
    relay.idle()
    return window


def put(relay, window, node, output="pressed", yes=None, **payload):
    """部品の出力を出す。yes を渡すと、出てきた確認に答える。"""
    relay.input(window, node, output, payload, human=True)
    if yes is not None:
        shown = answer(relay, window, yes)
        relay.idle()
        return shown
    relay.idle()


def inside(relay, screen):
    """窓の中に重ねて開いた画面（いちばん新しいもの）。"""
    found = [w for w in relay.display.windows() if w["screen"] == screen and w.get("parent")]
    assert found, f"{screen} が、窓の中に開いていません"
    return found[-1]


def called(relay, name):
    """そのコマンドを呼んだときの引数（呼んだ順）。"""
    return [args for command, args in relay.backend.calls if command == name]


def wrap(relay, window, node):
    return (nodes(relay, window)[node]["wrap"] or {}).get("kind")


def notices(relay):
    return [event["message"] for event in relay.display.events_after(0) if event["command"] == "notify"]


# --- ブランチ同士の取り込み（merge・review-branch-merge） ---------------------------------------

def test_merge_card_reads_the_plan_for_the_pair_and_takes_in(relay):
    window = opened(relay, "review-branch-merge", name="main")
    view = nodes(relay, window)
    assert [b["name"] for b in view["pick"]["props"]["branches"]] == ["main", "dev", "release", "task/12-login"]
    assert view["pick"]["props"]["name"] == "main" and view["pick"]["props"]["default_base"] == "main" and view["pick"]["props"]["side"] == "into"
    assert relay.backend.plans == []  # 組が決まるまで、下見は読まない
    assert [wrap(relay, window, node) for node in ("plan", "go")] == ["hidden", "hidden"]  # 畳んだカード：中は出さない
    with pytest.raises(Exception):
        relay.input(window, "pick", "changed", {"source": "main", "into": "main"}, human=True)  # 同じブランチ同士は選べない

    put(relay, window, "pick", "changed", source="dev", into="main")  # 部品が、初めの相手を選んで出す
    view = nodes(relay, window)
    assert (view["pick"]["props"]["source"], view["pick"]["props"]["into"]) == ("dev", "main")
    assert set(map(str, relay.backend.plans)) == {str(("branch merge", {"name": "dev", "into": "main"}))}  # 読むのは、選んだ組の下見だけ
    assert view["plan"]["props"]["plan"]["method"] == "fast-forward" and view["pick"]["props"]["plan"]["commit_count"] == 2
    assert not called(relay, "branch merge")  # 下見は、何も変えない
    put(relay, window, "pick", "toggled", open=True)  # することがあるので、部品がカードを開ける
    assert nodes(relay, window)["pick"]["props"]["open"] is True
    assert [wrap(relay, window, node) for node in ("plan", "go", "merge", "resolve")] == [None, None, None, "hidden"]

    shown = put(relay, window, "merge", yes=False)  # 取り込む：確かめてから
    assert shown["part"] == "confirm-box" and not called(relay, "branch merge")
    put(relay, window, "merge", yes=True)
    assert called(relay, "branch merge") == [{"name": "dev", "into": "main"}] and relay.backend.modules[-1] == CALC
    assert relay.display.values(window)["merge_into"] == "main"  # 組はそのまま（読み直した下見が出る）
    assert "ブランチを取り込みました。" in notices(relay)

    # 向きを入れ替える（→）：下見を読み直す。確かめ直す：読み直す
    put(relay, window, "pick", "changed", source="main", into="dev")
    assert relay.backend.plans[-1] == ("branch merge", {"name": "main", "into": "dev"})
    count = len(relay.backend.plans)
    put(relay, window, "pick", "reload")
    assert len(relay.backend.plans) == count + 1
    put(relay, window, "pick", "toggled", open=False)  # 手で畳む
    assert wrap(relay, window, "plan") == "hidden"


def test_merge_card_offers_the_task_that_fixes_a_conflict(relay):
    window = opened(relay, "review-branch-merge", name="dev", side="from")
    assert nodes(relay, window)["pick"]["props"]["side"] == "from"
    put(relay, window, "pick", "changed", source="dev", into="release")
    put(relay, window, "pick", "toggled", open=True)
    view = nodes(relay, window)
    assert view["plan"]["props"]["plan"]["conflicts"] == ["src/app.py"]
    assert [wrap(relay, window, node) for node in ("merge", "resolve")] == ["hidden", None]  # 衝突するとき：「衝突を直す…」だけ
    put(relay, window, "resolve")
    form = inside(relay, "review-branch-resolve")
    assert form["args"] == {"module": CALC, "name": "dev", "into": "release"}
    props = nodes(relay, form["id"])["form"]["props"]
    assert props["vars"] == {"name": "dev", "into": "release"} and "{into} を {name} へ取り込むタスク" in props["intro"]
    put(relay, form["id"], "form", "submitted", values={})
    assert called(relay, "branch resolve") == [{"name": "dev", "into": "release"}]
    assert any("衝突を直すタスク #31 を作りました" in notice for notice in notices(relay))
    assert not [w for w in relay.display.windows() if w["screen"] == "review-branch-resolve"]  # うまくいったら閉じる


def test_merge_page_holds_the_card_and_the_forms_of_the_submission(relay):
    window = opened(relay, "merge", name="dev")
    view = nodes(relay, window)
    assert view["nav"]["props"]["current"] == "branches" and view["title"]["props"]["text"] == "dev"
    pick = view["card:pick"]["props"]
    assert (pick["name"], pick["side"], pick["foldable"]) == ("dev", "from", False)  # ページでは、選んだブランチが取り込む側・畳まない
    put(relay, window, "card:pick", "changed", source="dev", into="main")
    put(relay, window, "card:pick", "toggled", open=True)
    assert nodes(relay, window)["card:plan"]["props"]["plan"]["into"] == "main"

    put(relay, window, "submit")  # 提出する…：取り込み先（初めは、カードで選んでいるもの）と題名の入力の窓
    form = inside(relay, "review-branch-submit")
    assert form["args"] == {"module": CALC, "name": "dev", "into": "main"}
    props = nodes(relay, form["id"])["form"]["props"]
    assert props["initial"] == {"into": "main"} and [row["name"] for row in props["rows"]][:2] == ["main", "dev"]
    put(relay, form["id"], "form", "submitted", yes=True, values={"into": "release", "title": "11月の分"})
    assert called(relay, "branch submit") == [{"name": "dev", "into": "release", "title": "11月の分"}]

    put(relay, window, "merge_submission")  # 作ってある提出の取り込み：入力の窓（CI が失敗していても取り込むか）
    form = inside(relay, "review-merge")
    assert form["args"] == {"module": CALC, "name": "dev"}
    put(relay, form["id"], "form", "submitted", yes=True, values={"ignore_checks": True})
    assert called(relay, "branch merge")[-1] == {"name": "dev", "ignore_checks": True}  # 取り込み先を付けない：提出を取り込む

    put(relay, window, "back")  # ブランチの一覧へ戻る（同じ窓）
    assert relay.display.tree(window)["screen"] == "branches"
