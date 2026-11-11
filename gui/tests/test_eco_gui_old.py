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
        flag, many = {"type": "boolean"}, {"type": "array", "items": text}
        pairs = ("define", "public_define", "include", "source_dir", "system_lib", "compile_option", "link_option", "conditional_define",
                 "build_event", "output_file")
        return {
            **super()._specs(text),
            # 本物の一覧と同じ引数（C++ の型のコマンド）
            "project set": spec("change", projects=text, project=text, kind=text, no_test=flag, type=text, export_all=text, entry_point=text, gui=text,
                                compiler=text, configuration=text, warning_level=text, warnings_as_errors=text, event=text, folder=text, clear_folder=flag,
                                **{f"{verb}_{name}": text for name in pairs for verb in ("add", "remove")}),
            "project link": spec("change", library=many, project=text, type=text, package=text, cmake=text, target=text, directory=text,
                                 file=text, implib=text, include=text),
            "project pch": spec("change", projects=text, project=text, off=flag, header=text, system=text),
            "module settings": spec("read", main=text, no_main=flag, projects_folder=text, linked_folder=text, external_folder=text, msvc_runtime=text),
            "check": spec("read", build=flag, only=text, tests=text),
            "run": spec("change", argv=many, projects=text, project=text, configuration=text, profile=text, arguments=text),
            "branch resolve": spec("change", ["name"], name=text, into=text),
            "branch submit": spec("confirm", ["name"], name=text, into=text, title=text),
            "branch merge": {**spec("confirm", ["name"], name=text, into=text, ignore_checks=flag), "dry_run": True},
        }

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


# --- C++：Project・依存先・全般・テンプレート（cpp と、入力の窓 mod-cpp-…） -------------------------

PLACE = "C:/work/Calc/.ecobuild/w/12"  # タスクブランチの作業空間（偽の module show が答えるもの）


def form(relay, window, node, name, screen, target="", value=""):
    """表の操作から、入力の窓を開く。"""
    put(relay, window, node, "action", name=name, target=target, value=value)
    return inside(relay, screen)


def decide(relay, opened_form, yes=None, **values):
    """入力の窓で、変更する作業空間を選んで決める。"""
    put(relay, opened_form["id"], "form", "submitted", yes=yes, values={"place": PLACE, **values})


def ran_in(relay, name):
    """そのコマンドを実行した場所（最後のもの）。"""
    return [module for module, call in zip(relay.backend.modules, relay.backend.calls) if call[0] == name][-1]


def test_cpp_page_gives_the_tables_what_they_draw(relay):
    window = opened(relay, "cpp", GAME)  # モジュール › Project
    view = nodes(relay, window)
    assert view["projects"]["props"]["view"] == "projects" and not {"deps", "general", "templates"} & set(view)
    assert [p["name"] for p in view["projects"]["props"]["projects"]] == ["Calc", "CalcTest"] and view["projects"]["props"]["settings"]["main_project"] == "Calc"
    assert view["projects"]["props"]["deps"][0]["name"] == "Math"  # リンクの印の色（依存先かどうか）に使う
    assert (view["nav"]["props"]["current"], view["section"]["props"]["current"]) == ("overview", "cpp") and relay.backend.modules[-1] == GAME
    assert view["section"]["props"]["kind"] == "cpp"  # C++ のモジュール：上のタブに Project・依存先が出る
    put(relay, window, "update")
    assert called(relay, "project update") == [{}]

    put(relay, window, "section", "selected", id="cpp-deps")  # モジュール › 依存先（同じ窓で）
    view = nodes(relay, window)
    assert relay.display.tree(window)["screen"] == "cpp-deps" and (view["nav"]["props"]["current"], view["section"]["props"]["current"]) == ("overview", "cpp-deps")
    assert view["deps"]["props"]["deps"][0]["state"] == "aligned" and view["deps"]["props"]["tree"]["direct"] == ["Math"]
    assert view["deps"]["props"]["projects"][0]["name"] == "Calc"  # 使っている Project の列
    assert ("deps list", {}) in relay.backend.calls and not called(relay, "deps versions")  # 開いただけでは、GitHub に聞かない
    put(relay, window, "deps", "action", name="deps_fetch")  # GitHub と照らし合わせる：--fetch で読み直し、列を足す
    assert ("deps list", {"fetch": True}) in relay.backend.calls and nodes(relay, window)["deps"]["props"]["fetched"] is True

    window = opened(relay, "settings", GAME)  # 設定：C++ の設定・ファイルテンプレートのタブ
    view = nodes(relay, window)
    assert view["cpp_general"]["props"]["settings"]["msvc_runtime"] == "dll" and "templates" in view["cpp_templates"]["props"]["settings"]
    assert view["cpp_general"].get("wrap") is None and view["cpp_templates"].get("wrap") is None  # C++ のモジュールでは出る


def test_cpp_projects_are_added_changed_linked_moved_and_removed_in_a_workspace(relay):
    window = opened(relay, "cpp", GAME)
    added = form(relay, window, "projects", "project_add", "mod-cpp-project-add")
    props = nodes(relay, added["id"])["form"]["props"]
    assert [row["name"] for row in props["rows"]] == ["Calc", "CalcTest"] and props["more"][0]["path"] == PLACE  # リンクするライブラリ・変更する作業空間
    decide(relay, added, name="Math", kind="library", test=False, no_test=True)
    assert called(relay, "project add")[-1] == {"name": "Math", "kind": "library", "no_test": True} and ran_in(relay, "project add") == PLACE  # 作業空間で実行

    settings = form(relay, window, "projects", "project_settings", "mod-cpp-project-settings", target="Calc")
    assert settings["args"] == {"module": GAME, "name": "Calc"}
    assert nodes(relay, settings["id"])["form"]["props"]["vars"]["source_directories"] == ["src"]  # 今の設定（project show）を上に出す
    assert ("project show", {"project": "Calc"}) in relay.backend.calls
    decide(relay, settings, kind="", add_define="USE_FOO,LEVEL=2", remove_include="old", warning_level="4", entry_point="")
    assert called(relay, "project set")[-1] == {"project": "Calc", "add_define": "USE_FOO,LEVEL=2", "remove_include": "old", "warning_level": "4"}  # 空の欄は渡さない

    link = form(relay, window, "projects", "project_link", "mod-cpp-project-link", target="CalcTest")
    decide(relay, link, what="project", library=["Calc"], type="static")
    assert called(relay, "project link")[-1] == {"project": "CalcTest", "library": ["Calc"], "type": "static"}
    link = form(relay, window, "projects", "project_link", "mod-cpp-project-link", target="Calc")
    decide(relay, link, what="package", package="fmt", directory="third_party/fmt", target="fmt::fmt")
    assert called(relay, "project link")[-1] == {"project": "Calc", "package": "fmt", "directory": "third_party/fmt", "target": "fmt::fmt"}

    unlink = form(relay, window, "projects", "project_unlink", "mod-cpp-project-unlink", target="Calc")
    assert nodes(relay, unlink["id"])["form"]["props"]["rows"] == [{"id": "g-1", "kind": "library", "name": "Math", "as": "static"}]  # 今のリンクから選ぶ
    decide(relay, unlink, link="g-1")
    assert called(relay, "project unlink") == [{"link": "g-1", "project": "Calc"}]

    pch = form(relay, window, "projects", "project_pch", "mod-cpp-project-pch", target="Calc")
    decide(relay, pch, off=False, header="", system="vector, string")
    assert called(relay, "project pch")[-1] == {"project": "Calc", "off": False, "system": "vector, string"}
    pch = form(relay, window, "projects", "project_pch", "mod-cpp-project-pch", target="Calc")
    decide(relay, pch, off=True)
    assert called(relay, "project pch")[-1] == {"project": "Calc", "off": True}

    move = form(relay, window, "projects", "project_move", "mod-cpp-project-move", target="Calc")
    decide(relay, move, destination="libs/Calc")
    assert called(relay, "project move") == [{"name": "Calc", "destination": "libs/Calc"}]

    remove = form(relay, window, "projects", "project_remove", "mod-cpp-project-remove", target="CalcTest")
    assert nodes(relay, remove["id"])["form"]["props"]["danger"] is True
    decide(relay, remove, yes=True)  # 削除は、本体が確かめてから
    assert called(relay, "project remove") == [{"name": "CalcTest"}]
    for name in ("project set", "project link", "project unlink", "project pch", "project move", "project remove"):
        assert ran_in(relay, name) == PLACE
    assert not [w for w in relay.display.windows() if w.get("parent")]  # うまくいった窓は閉じている


def test_cpp_dependencies_are_linked_updated_picked_and_removed(relay):
    window = opened(relay, "cpp-deps", GAME)
    add = form(relay, window, "deps", "dep_add", "mod-cpp-dep-add")
    decide(relay, add, repository="acme/Net", project="", shared=True, at="v1.2.0")
    assert called(relay, "deps add") == [{"repository": "acme/Net", "shared": True, "at": "v1.2.0"}]

    update = form(relay, window, "deps", "dep_update", "mod-cpp-dep-update", target="Math")
    assert nodes(relay, update["id"])["form"]["props"]["initial"] == {"place": GAME, "name": "Math", "at": ""}
    decide(relay, update, name="Math", at="")
    assert called(relay, "deps update")[-1] == {"name": "Math"}
    update = form(relay, window, "deps", "deps_update", "mod-cpp-dep-update")  # すべて更新：名前なし
    decide(relay, update, name="", at="")
    assert called(relay, "deps update")[-1] == {}

    # 版を選ぶ：押したときに読む（GitHub から取り込み直す）。ブランチを変えると、そのブランチで読み直す
    put(relay, window, "deps", "action", name="dep_versions", target="Math", value="")
    assert called(relay, "deps versions") == [{"name": "Math"}]
    versions = nodes(relay, window)["deps"]["props"]["versions"]
    assert versions["name"] == "Math" and [c["sha"] for c in versions["commits"]] == ["fff", "abc"] and versions["branches"] == ["main", "dev"]
    put(relay, window, "deps", "action", name="dep_versions", target="Math", value="dev")
    assert called(relay, "deps versions")[-1] == {"name": "Math", "branch": "dev"}
    pick = form(relay, window, "deps", "dep_use", "mod-cpp-dep-update", target="Math", value="fff")  # この版にする：確かめの窓に、名前と版が入っている
    assert pick["args"] == {"module": GAME, "name": "Math", "at": "fff"}
    decide(relay, pick, name="Math", at="fff")
    assert called(relay, "deps update")[-1] == {"name": "Math", "at": "fff"}
    assert nodes(relay, window)["deps"]["props"].get("versions") is None  # 記録したら、版を選ぶ所を閉じる
    put(relay, window, "deps", "action", name="dep_versions", target="Math", value="")
    put(relay, window, "deps", "action", name="dep_versions_close", target="Math")
    assert nodes(relay, window)["deps"]["props"].get("versions") is None

    sync = form(relay, window, "deps", "deps_sync", "mod-cpp-dep-sync")
    put(relay, sync["id"], "form", "submitted", values={})
    assert called(relay, "deps sync") == [{}] and ran_in(relay, "deps sync") == GAME  # 手元を合わせるだけ：モジュールの場所で

    remove = form(relay, window, "deps", "dep_remove", "mod-cpp-dep-remove", target="Math")
    decide(relay, remove)
    assert called(relay, "deps remove") == [{"name": "Math"}]


def test_cpp_settings_and_templates_are_changed_with_their_forms(relay):
    window = opened(relay, "settings", GAME)
    settings = form(relay, window, "cpp_general", "module_settings", "mod-cpp-settings")
    props = nodes(relay, settings["id"])["form"]["props"]
    assert props["values"]["main_project"] == "Calc" and [row["name"] for row in props["rows"]] == ["Calc", "CalcTest"]  # 今の値と、選べる Project
    decide(relay, settings, main="Calc", no_main=False, msvc_runtime="static", projects_folder="", linked_folder="Linked", external_folder="")
    assert called(relay, "module settings")[-1] == {"main": "Calc", "no_main": False, "msvc_runtime": "static", "linked_folder": "Linked"}

    add = form(relay, window, "cpp_templates", "template_add", "mod-cpp-template-add")
    decide(relay, add, name="widget", source="templates/widget.h")
    assert called(relay, "template add") == [{"name": "widget", "source": "templates/widget.h"}]
    replace = form(relay, window, "cpp_templates", "template_replace", "mod-cpp-template-add", target="header")
    assert nodes(relay, replace["id"])["form"]["props"]["initial"]["name"] == "header"  # 差し替え：名前が入っている
    put(relay, replace["id"], "form", "cancelled")
    remove = form(relay, window, "cpp_templates", "template_remove", "mod-cpp-template-remove", target="widget")
    decide(relay, remove)
    assert called(relay, "template remove") == [{"name": "widget"}]
    with pytest.raises(Exception):
        relay.input(window, "cpp_templates", "action", {"name": ""}, human=True)  # 操作の名前のない入力は断る


def test_overview_opens_the_cpp_page_in_the_same_window(relay):
    window = opened(relay, "overview", GAME)
    put(relay, window, "about", "opened", page="deps")
    tree = relay.display.tree(window)
    assert (tree["screen"], tree["args"]) == ("cpp-deps", {"module": GAME})


# --- ビルドと試験（build） ---------------------------------------------------------------------

def test_build_window_chooses_the_configuration_the_profile_the_target_and_the_arguments(relay):
    window = opened(relay, "build", GAME)
    setting = nodes(relay, window)["setting"]["props"]
    assert setting["profiles"]["selected"] == "fast" and setting["module_type"] == "cpp"
    put(relay, window, "setting", "profile", name="ship")  # この PC で使うビルド設定（ecobuild profile use）
    assert called(relay, "profile use") == [{"name": "ship"}] and nodes(relay, window)["setting"]["props"]["profiles"]["selected"] == "ship"
    put(relay, window, "setting", "profile", name="none")
    assert called(relay, "profile use")[-1] == {"name": "none"}
    with pytest.raises(Exception):
        relay.input(window, "setting", "profile", {"name": ""}, human=True)

    put(relay, window, "setting", "configuration", value="Release")
    put(relay, window, "setting", "target", project="Calc")
    put(relay, window, "setting", "arguments", text="--size 3")
    setting = nodes(relay, window)["setting"]["props"]
    assert (setting["configuration"], setting["target"], setting["arguments"]) == ("Release", "Calc", "--size 3")
    put(relay, window, "build")
    assert called(relay, "build") == [{"configuration": "Release", "project": "Calc"}] and ran_in(relay, "build") == GAME
    out = nodes(relay, window)["out"]["props"]
    assert (out["title"], out["kind"], out["state"]) == ("ビルド", "build", "ok") and out["result"]["artifacts"] == ["dist/calc-1.0-py3-none-any.whl"]
    put(relay, window, "run")
    assert called(relay, "run") == [{"configuration": "Release", "arguments": "--size 3", "project": "Calc"}]
    out = nodes(relay, window)["out"]["props"]
    assert (out["title"], out["kind"], out["result"]["returncode"]) == ("実行", "run", 0)
    for button in ("rebuild", "clean"):
        put(relay, window, button)
        assert called(relay, button) == [{"configuration": "Release", "project": "Calc"}]
    put(relay, window, "check")
    assert called(relay, "check")[-1] == {} and nodes(relay, window)["out"]["props"]["title"] == "提出前の確認"

    put(relay, window, "setting", "configuration", value="")  # ビルド設定のまま：構成を渡さない
    put(relay, window, "setting", "target", project="")
    put(relay, window, "build")
    assert called(relay, "build")[-1] == {}
    put(relay, window, "setting", "settings")  # ビルド設定の追加・編集は、モジュールの「設定」
    assert [w["screen"] for w in relay.display.windows() if w["id"] != window] == ["settings"]


def test_build_window_runs_the_checked_and_the_named_tests_and_shows_the_result(relay):
    window = opened(relay, "build")
    assert not called(relay, "tests") and nodes(relay, window)["tests"]["props"]["rows"] == []  # 開いただけでは集めない
    put(relay, window, "tests_load")
    assert called(relay, "tests") == [{}] and len(nodes(relay, window)["tests"]["props"]["rows"]) == 3
    put(relay, window, "tests", "changed", values=["tests/test_app.py"])
    put(relay, window, "test_checked")
    assert called(relay, "test")[-1] == {"tests": ["tests/test_app.py"]}
    view = nodes(relay, window)
    assert (view["out"]["props"]["title"], view["out"]["props"]["state"], view["out"]["props"]["result"]["passed"]) == ("テスト（選んだもの）", "ok", 2)
    assert view["tests"]["props"]["last"]["skipped"] == 1 and "2 passed" in "".join(view["out"]["props"]["lines"])  # 木に前の結果、出力欄に道具の出力

    assert wrap(relay, window, "test_named") == "unavailable"  # 名前を書くまで押せない
    put(relay, window, "test_name", "changed", text="tests/test_login.py")
    put(relay, window, "test_named")
    assert called(relay, "test")[-1] == {"tests": ["tests/test_login.py"]} and nodes(relay, window)["out"]["props"]["title"] == "テスト（名前で指定）"
    put(relay, window, "filter", "changed", text="login and not slow")
    put(relay, window, "last_failed", "changed", on=True)
    put(relay, window, "test_filtered")
    assert called(relay, "test")[-1] == {"filter": "login and not slow", "last_failed": True}
    put(relay, window, "test")
    assert called(relay, "test")[-1] == {}

    relay.backend.failing = True  # 失敗：出力欄の印が「失敗」になる
    put(relay, window, "test")
    assert nodes(relay, window)["out"]["props"]["state"] == "bad"


# --- 退避の一覧・注釈履歴（stashes・blame） -------------------------------------------------------

def test_stashes_window_stashes_pops_and_drops_by_number(relay):
    relay.backend.stashes = ["On task/12-login: 3つ目", "On main: 試し", "On task/12-login: 1つ目"]
    window = opened(relay, "stashes", PLACE)
    props = nodes(relay, window)["list"]["props"]
    assert props["stashes"] == relay.backend.stashes and props["status"]["branch"] == "task/12-login"  # このブランチのものを分けるのは、部品
    put(relay, window, "list", "action", name="pop", index=2)
    assert called(relay, "stash pop") == [{"index": 2}] and ran_in(relay, "stash pop") == PLACE
    assert nodes(relay, window)["list"]["props"]["stashes"] == ["On task/12-login: 3つ目", "On main: 試し"]  # 変えたら読み直す
    shown = put(relay, window, "list", "action", name="drop", index=0, yes=False)  # 削除は、確かめてから
    assert shown["part"] == "confirm-box" and not called(relay, "stash drop")
    put(relay, window, "list", "action", name="drop", index=0, yes=True)
    assert called(relay, "stash drop") == [{"index": 0}]
    put(relay, window, "list", "action", name="stash")
    assert called(relay, "stash") == [{}]
    for bad in ({"name": "pop"}, {"name": "clear", "index": 0}):
        with pytest.raises(Exception):
            relay.input(window, "list", "action", bad, human=True)  # 番号のない戻す・知らない操作は断る


def test_blame_window_marks_a_commit_and_opens_its_change_and_the_log(relay):
    window = opened(relay, "blame", PLACE, path="src/app.py")
    view = nodes(relay, window)
    assert view["lines"]["props"]["text"].startswith("abc12345 (octocat 2026-11-01  1)") and view["title"]["props"]["text"] == "src/app.py"
    assert ("blame", {"path": "src/app.py"}) in relay.backend.calls
    put(relay, window, "lines", "selected", commit="abc12345")
    assert nodes(relay, window)["lines"]["props"]["selected"] == "abc12345"
    put(relay, window, "lines", "opened", commit="abc12345")  # もう一度押す：そのコミットの変更を、窓の中に重ねて開く
    assert inside(relay, "ws-show")["args"] == {"module": PLACE, "commit": "abc12345"}
    put(relay, window, "log")  # このファイルのログ（別の窓）
    log = [w for w in relay.display.windows() if w["screen"] == "ws-log"][-1]
    assert log["args"]["paths"] == ["src/app.py"] and log["args"]["module"] == PLACE
    put(relay, window, "external")
    assert ("blame", {"path": "src/app.py", "gui": True}) in relay.backend.calls


def test_the_removed_screens_are_gone_and_the_new_parts_declare_their_outputs():
    app = create_app(importlib.import_module("eco_gui"), backend=OldEcobuild(), roles={"confirm": "confirm-box"})
    described = app.describe()
    screens = {screen["name"] for screen in described["screens"]}
    assert not {"files", "hub-archive"} & screens  # 入口のなくなった画面（役目は、作業空間のエクスプローラーとハブのカードのメニュー）
    assert {"merge", "review-branch-merge", "cpp", "build", "stashes", "blame"} <= screens
    parts = {part["name"]: part for part in described["parts"]}
    assert set(parts["review-merge-pick"]["outputs"]) == {"changed", "toggled", "reload"}
    assert set(parts["mod-cpp"]["outputs"]) == {"action", "reload"}
    assert set(parts["ws-build-setting"]["outputs"]) == {"configuration", "profile", "target", "arguments", "settings"}
    assert set(parts["ws-stashes"]["outputs"]) == {"action", "reload"} and set(parts["ws-blame"]["outputs"]) == {"selected", "opened"}
