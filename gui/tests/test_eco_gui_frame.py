"""eco_gui のモジュールの窓の枠（左のメニューの「作業空間」・作業空間のタブ・既定のブランチにいないときの帯）と、
この PC の道具で開く（ecobuild open）：窓の作りと、画面が、人が打つのと同じコマンドを正しい引数で呼ぶこと。

ecobuild は呼ばない（偽のバックエンドで確かめる）。
"""

import importlib

import pytest

pytest.importorskip("guiframework")

from guiframework import create_app  # noqa: E402

from test_eco_gui import FakeEcobuild, answer, nodes  # noqa: E402
from test_eco_gui_polish import last, notices, opened, press, spec  # noqa: E402
from test_eco_gui_workspace import WorkspaceEcobuild  # noqa: E402

MODULE = "C:/work/Calc"
PLACE = "C:/work/Calc/.ecobuild/w/12"
OTHER = "C:/work/Calc/.ecobuild/w/15"


class FrameCommands(FakeEcobuild):
    """足したコマンドの形（本物の一覧に合わせてある）。ほかの試験の偽のバックエンドも、ここから集める。"""

    def _specs(self, text):
        return {
            **super()._specs(text),
            "open": {**spec("change", path={"type": "array", "items": text}, app=text, vs_version=text, line={"type": "integer"}), "can": True},
            "workspace close": spec("confirm", at=text, discard_local={"type": "boolean"}),
            "task push": spec("change", force={"type": "boolean"}, pipelines={"type": "boolean"}),
            "log": spec("read", paths={"type": "array", "items": text}, count={"type": "integer"}, branch=text, unpushed={"type": "boolean"}),
        }


class FrameEcobuild(WorkspaceEcobuild):
    """モジュールの窓の枠が読むもの（作業空間の一覧・この PC の道具）を足した、ecobuild の代わり。"""

    def __init__(self):
        super().__init__()
        self.studios = {"2026": (True, ""), "2022": (False, "Visual Studio 2022 が、この PC に見つかりません。あるのは 2026 です。")}

    def run(self, name, args, context, on_event):
        result = super().run(name, args, context, on_event)
        if name == "module show":
            return {"ok": True, "result": {"name": "Calc", "type": "python", "private": True, "projects": [], "workspaces": [
                {"name": "12", "path": PLACE, "branch": "task/12-login", "task": 12, "account": None, "review": None},
                {"name": "15", "path": OTHER, "branch": "task/15-search", "task": 15, "account": None, "review": None}]}}
        if name == "workspace list":
            return {"ok": True, "result": {"modules": [{"path": MODULE, "exists": True, "type": "python", "branch": "task/9-x", "default_branch": "main",
                                                        "workspaces": []}], "legacy": []}}
        return result

    def can(self, name, args):
        if name == "open" and args.get("app") == "vs":
            return self.studios[args["vs_version"]]
        return True, ""


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=FrameEcobuild(), roles={"confirm": "confirm-box"})
    relay = app.relay(threaded=True)
    relay.verify()  # どの画面のつなぎも、バックエンドのコマンドと合っている
    return relay


def screen_of(relay, window):
    tree = relay.display.tree(window)
    return tree["screen"], tree["args"]


def test_the_menu_has_the_workspaces_and_the_page_shows_their_tabs(relay):
    window = opened(relay, "overview", MODULE)
    assert "frame-workspaces" in [item["id"] for item in nodes(relay, window)["nav"]["props"]["items"]]
    press(relay, window, "nav", "selected", id="frame-workspaces")
    view = nodes(relay, window)
    assert screen_of(relay, window)[0] == "frame-workspaces" and view["nav"]["props"]["current"] == "frame-workspaces"
    assert view["main"]["children"] == ["bar"] and view["bar"]["children"] == ["bar:band", "bar:tabs"]
    tabs = view["bar:tabs"]["props"]
    assert [w["path"] for w in tabs["workspaces"]] == [PLACE, OTHER] and tabs["tasks"][0]["title"] == "ログイン画面"  # タブの題は、タスクの題
    assert tabs["current"] == "" and tabs["closed"] == []
    # Visual Studio の版ごとに、開けるか（入っていない版は、メニューで灰色と理由）
    assert tabs["vs2026"] == {"can": True, "reason": ""} and tabs["vs2022"]["can"] is False and "2022" in tabs["vs2022"]["reason"]
    # 帯：モジュールのフォルダーが既定のブランチにいるかは、この PC のモジュールの一覧から
    band = view["bar:band"]["props"]
    assert band["module"] == MODULE and band["modules"][0]["default_branch"] == "main"
    assert [w["id"] for w in relay.display.windows()] == [window] and notices(relay) == []


def test_choosing_a_tab_shows_that_workspace_in_the_same_window(relay):
    window = opened(relay, "frame-workspaces", MODULE)
    press(relay, window, "bar:tabs", "selected", path=PLACE, closed=[])
    assert screen_of(relay, window) == ("frame-workspace", {"module": MODULE, "space": PLACE, "closed": []})
    view = nodes(relay, window)
    assert view["main"]["children"] == ["bar", "ws"] and view["bar:tabs"]["props"]["current"] == PLACE
    # 中身は、作業空間の画面そのもの（その作業空間で読む）
    assert (view["ws"]["look"], view["ws"]["children"]) == ("ws-window", ["ws:state", "ws:toolbar", "ws:body", "ws:foot"])
    assert view["ws:state"]["props"]["data"]["branch"] == "task/12-login" and view["ws:explorer"]["part"] == "ws-explorer"
    assert ("status", {}) in relay.backend.calls and PLACE in relay.backend.modules
    # 別のタブへ：同じ窓のまま、閉じたタブも運ぶ
    press(relay, window, "bar:tabs", "selected", path=OTHER, closed=[PLACE])
    assert screen_of(relay, window) == ("frame-workspace", {"module": MODULE, "space": OTHER, "closed": [PLACE]})
    assert nodes(relay, window)["bar:tabs"]["props"]["closed"] == [PLACE]
    # 出すタブがなくなった：案内の画面へ
    press(relay, window, "bar:tabs", "emptied", closed=[PLACE, OTHER])
    assert screen_of(relay, window) == ("frame-workspaces", {"module": MODULE, "closed": [PLACE, OTHER]})
    assert [w["id"] for w in relay.display.windows()] == [window] and notices(relay) == []


def test_the_workspace_in_the_tab_works_in_its_own_folder(relay):
    window = opened(relay, "frame-workspace", MODULE, space=PLACE)
    press(relay, window, "ws:changes", "changed", paths=["a.py"])
    press(relay, window, "ws:commit_box", "changed", text="直した")
    relay.backend.modules.clear()
    press(relay, window, "ws:commit_box", "commit")
    assert last(relay) == ("task commit", {"paths": ["a.py"], "message": "直した"}) and relay.backend.modules[0] == PLACE


def test_the_tab_menu_opens_the_folder_and_removes_the_workspace(relay):
    window = opened(relay, "frame-workspace", MODULE, space=PLACE)
    relay.backend.modules.clear()
    press(relay, window, "bar:tabs", "action", name="explorer", path=OTHER)
    assert last(relay) == ("open", {"app": "explorer"}) and relay.backend.modules[0] == OTHER  # その作業空間のフォルダーを開く
    press(relay, window, "bar:tabs", "action", name="vs", path=OTHER, version="2026")
    assert last(relay) == ("open", {"app": "vs", "vs_version": "2026"})
    # 作業空間を削除：確かめてから、モジュールの側で ecobuild workspace close --at <場所>
    relay.backend.modules.clear()
    relay.input(window, "bar:tabs", "action", {"name": "remove", "path": OTHER}, human=True)
    answer(relay, window, False)
    assert last(relay)[0] != "workspace close"
    relay.input(window, "bar:tabs", "action", {"name": "remove", "path": OTHER}, human=True)
    answer(relay, window, True)
    assert last(relay) == ("workspace close", {"at": OTHER}) and MODULE in relay.backend.modules
    # タスクを表示・タスク管理を開く：同じ窓で
    press(relay, window, "bar:tabs", "action", name="task", path=PLACE, task=12)
    assert screen_of(relay, window)[0] == "tasks" and [w["id"] for w in relay.display.windows()] == [window]


def test_the_workspace_opens_files_with_the_tools_of_this_pc(relay):
    window = opened(relay, "workspace", PLACE)
    bar = nodes(relay, window)["toolbar"]["props"]
    assert bar["vs2026"]["can"] is True and bar["vs2022"]["can"] is False  # ▾ で、入っていない版は灰色と理由
    press(relay, window, "toolbar", "action", name="open_folder")
    assert last(relay) == ("open", {"app": "explorer"})
    press(relay, window, "toolbar", "action", name="open_vs", value="2026")
    assert last(relay) == ("open", {"app": "vs", "vs_version": "2026"})
    # ダブルクリック：開発の道具で（版は、まだ選んでいなければ渡さない＝この PC のいちばん新しい版）
    press(relay, window, "explorer", "action", name="open", path="src/app.py", paths=["src/app.py"])
    assert last(relay) == ("open", {"path": ["src/app.py"], "app": "editor"})
    # ツールバーで版を選ぶと、ファイルを開くときも、その版
    press(relay, window, "toolbar", "action", name="vs_version", value="2026")
    assert nodes(relay, window)["toolbar"]["props"]["vs_version"] == "2026"
    press(relay, window, "explorer", "action", name="open_vs", path="src/app.py", paths=["src/app.py"])
    assert last(relay) == ("open", {"path": ["src/app.py"], "app": "vs", "vs_version": "2026"})
    press(relay, window, "explorer", "action", name="open_default", path="README.md", paths=["README.md"])
    assert last(relay) == ("open", {"path": ["README.md"], "app": "default"})
    press(relay, window, "explorer", "action", name="reveal", path="src", paths=["src"])
    assert last(relay) == ("open", {"path": ["src"], "app": "explorer"})
    # 出力の「ファイル(行)」のリンク：その行を開く
    press(relay, window, "foot", "action", name="show_output")  # 出力欄は、最初はしまってある
    press(relay, window, "out", "opened", path="src/app.py", line=12)
    assert last(relay) == ("open", {"path": ["src/app.py"], "app": "editor", "line": 12, "vs_version": "2026"})
    assert all(module == PLACE for module in relay.backend.modules if module)


def test_the_push_tab_force_pushes_after_reading_what_happens(relay):
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "tabs", "selected", tab="push")
    press(relay, window, "force_push")
    dialog = next(w["id"] for w in relay.display.windows() if w["screen"] == "ws-force-push" and w.get("parent") == window)
    assert "task push" not in [call[0] for call in relay.backend.calls]  # 開いただけでは、何もしない
    press(relay, dialog, "push")
    assert last(relay) == ("task push", {"force": True})
    assert not [w for w in relay.display.windows() if w["screen"] == "ws-force-push"]  # うまくいったら閉じる


def test_the_log_shows_the_branch_that_is_chosen(relay):
    window = opened(relay, "ws-log", PLACE)
    view = nodes(relay, window)
    assert view["list"]["props"]["branches"][0]["name"] == "dev" and not view["list"]["props"]["branch"]
    assert ("log", {"paths": []}) in relay.backend.calls  # 選ぶまでは、今のブランチ
    press(relay, window, "list", "branch", name="dev")
    assert ("log", {"paths": [], "branch": "dev"}) in relay.backend.calls and nodes(relay, window)["list"]["props"]["branch"] == "dev"
    press(relay, window, "list", "branch", name="")
    assert relay.backend.calls[-1] == ("log", {"paths": []}) or ("log", {"paths": []}) in relay.backend.calls[-3:]
