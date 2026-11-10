"""eco_gui の作り込み（作業空間・ビルドと試験・退避・ファイル・C++）：画面が、人が打つのと同じコマンドを正しい引数で呼ぶこと。

ecobuild は呼ばない（偽のバックエンドで確かめる）。
"""

import importlib

import pytest

pytest.importorskip("guiframework")

from guiframework import create_app  # noqa: E402

from test_eco_gui import FakeEcobuild, answer, nodes  # noqa: E402


def spec(weight, required=(), **properties):
    return {"description": weight, "weight": weight, "args": {"type": "object", "required": list(required), "properties": properties}}


class PolishEcobuild(FakeEcobuild):
    """足した画面が呼ぶコマンドを足した、ecobuild の代わり（引数の形は本物の一覧に合わせてある）。"""

    def __init__(self):
        super().__init__()
        self.stashes = ["On task/12-login: 途中の変更", "On main: 試し"]
        self.selected = "fast"

    def _specs(self, text):
        many, flag = {"type": "array", "items": text}, {"type": "boolean"}
        build = {"configuration": text, "profile": text}
        return {
            **super()._specs(text),
            "profile list": spec("read"), "profile use": spec("change", ["name"], name=text), "profile remove": spec("change", ["name"], name=text),
            "build": spec("change", **build), "rebuild": spec("change", **build), "clean": spec("change", **build),
            "run": spec("change", argv=many, arguments=text, **build),
            "test": spec("change", tests=many, filter=text, last_failed=flag, list=flag, **build),
            "stash list": spec("read"), "stash": spec("change"),
            "stash pop": spec("change", number={"type": "integer"}, index={"type": "integer"}),
            "stash drop": spec("confirm", number={"type": "integer"}, index={"type": "integer"}),
            "tests": spec("read", project=text, **build),
            "restore": spec("confirm", paths=many, staged=flag, source=text),
            "task add": spec("change", paths=many, all=flag),
            "ignore": spec("change", patterns=many),
            "blame": spec("read", ["path"], path=text, gui=flag),
            "log": spec("read", paths=many, count={"type": "integer"}, branch=text),
            "file test": spec("change", ["path"], path=text, to=text),
            "module settings": spec("read", main=text),
            "project list": spec("read"), "project update": spec("change"),
            "project add": spec("change", ["name"], name=text, kind=text, link=text, no_test=flag),
            "project move": spec("change", ["name", "destination"], name=text, destination=text),
            "project remove": spec("confirm", ["name"], name=text),
            "deps list": spec("read", fetch=flag, all=flag), "deps sync": spec("change"),
            "deps add": spec("change", ["repository"], repository=text, project=text, shared=flag, at=text),
            "deps remove": spec("change", ["name"], name=text),
            "deps update": spec("change", names=many, name=text, at=text),
            "template list": spec("read"), "template remove": spec("change", ["name"], name=text),
            "template add": spec("change", ["name", "source"], name=text, source=text),
        }

    def run(self, name, args, context, on_event):
        result = super().run(name, args, context, on_event)
        args = {key: value for key, value in args.items() if key != "module"}
        if name == "profile list":
            return {"ok": True, "result": {"selected": self.selected, "profiles": {
                "fast": {"configuration": "Debug", "shared": False}, "ship": {"configuration": "Release", "shared": True}}}}
        if name == "profile use":
            self.selected = None if args["name"] == "none" else args["name"]
        if name == "stash list":
            return {"ok": True, "result": list(self.stashes)}
        if name in ("stash pop", "stash drop"):
            del self.stashes[args.get("index", 0)]  # 番号を省けば、最後に退避したもの
        if name == "tests":
            return {"ok": True, "result": {"tests": [
                {"name": "tests/test_app.py::test_add", "file": "tests/test_app.py", "line": 4},
                {"name": "tests/test_app.py::test_sub", "file": "tests/test_app.py", "line": 9},
                {"name": "tests/test_login.py::test_login", "file": "tests/test_login.py", "line": 3}]}}
        if name == "test":
            on_event({"event": "output", "message": "2 passed\n"})
        if name == "blame":
            return {"ok": True, "result": f"abc12345 (octocat 2026-11-01  1) {args['path']} の1行目"}
        if name == "module settings":
            return {"ok": True, "result": {"main_project": "Calc", "msvc_runtime": "dll", "folders": None, "templates": ["header"]}}
        if name == "project list":
            return {"ok": True, "result": [{"name": "Calc", "kind": "library", "directory": "Calc", "links": []},
                                           {"name": "CalcTest", "kind": "test", "directory": "CalcTest", "links": ["Calc"]}]}
        if name == "deps list":
            return {"ok": True, "result": [{"name": "Math", "state": "aligned", "recorded": "abc", "local": "abc", "url": "https://example.invalid/Math"}]}
        if name == "template list":
            return {"ok": True, "result": {"header": {"path": "header.h", "builtin": True}, "widget": {"path": "templates/widget.h", "builtin": False}}}
        return result


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=PolishEcobuild(), roles={"confirm": "confirm-box"})
    relay = app.relay(threaded=True)
    relay.verify()  # どの画面のつなぎも、バックエンドのコマンドと合っている
    return relay


def opened(relay, screen, module="C:/work/Calc", **args):
    window = relay.execute({"command": "open", "screen": screen, "args": {"module": module, **args}})["window"]
    relay.idle()
    return window


def press(relay, window, node, output="pressed", **payload):
    relay.input(window, node, output, payload, human=True)
    relay.idle()


def last(relay):
    """最後に実行した、変えるコマンド（その後の読み直しは数えない）。"""
    reads = {name for name, spec in relay.backend.commands().items() if spec["weight"] == "read"}
    return [call for call in relay.backend.calls if call[0] not in reads][-1]


def notices(relay):
    return [event["message"] for event in relay.display.events_after(0) if event["command"] == "notify"]


def test_build_screen_selects_a_profile(relay):
    window = opened(relay, "build")
    view = nodes(relay, window)
    assert sorted(view["profiles"]["props"]["entries"]) == ["fast", "ship"] and view["profiles"]["props"]["current"] == "fast"
    assert relay.backend.calls.count(("profile list", {})) == 1  # 2つの要る情報へ出しても、読むのは1回
    press(relay, window, "profiles", "action", id="ship", action="use")
    assert ("profile use", {"name": "ship"}) in relay.backend.calls and relay.backend.modules[-1] == "C:/work/Calc"
    assert nodes(relay, window)["profiles"]["props"]["current"] == "ship"  # 変えたら読み直す
    press(relay, window, "no_profile")
    assert ("profile use", {"name": "none"}) in relay.backend.calls
    assert nodes(relay, window)["profiles"]["props"]["current"] is None
    press(relay, window, "profiles", "action", id="fast", action="remove")
    assert ("profile remove", {"name": "fast"}) in relay.backend.calls
    assert ("profile use", {"name": "fast"}) not in relay.backend.calls  # 押したボタンのコマンドだけ


def test_build_screen_passes_the_configuration_and_the_run_arguments(relay):
    window = opened(relay, "build")
    press(relay, window, "build")
    assert ("build", {}) in relay.backend.calls  # 構成を決めなければ、渡さない（ビルド設定のまま）
    assert nodes(relay, window)["out"]["props"]["lines"] == ["構成しています…", "ビルドしています…"]
    press(relay, window, "configuration", "changed", value="Release")
    assert nodes(relay, window)["configuration"]["props"]["value"] == "Release"
    for button in ("build", "rebuild", "clean"):
        press(relay, window, button)
        assert (button, {"configuration": "Release"}) in relay.backend.calls
    press(relay, window, "run_arguments", "changed", text="--verbose in.txt")
    press(relay, window, "run")
    assert ("run", {"configuration": "Release", "arguments": "--verbose in.txt"}) in relay.backend.calls
    press(relay, window, "configuration", "changed", value=None)  # 「ビルド設定のまま」に戻す
    press(relay, window, "clean")
    assert last(relay) == ("clean", {})
    assert notices(relay) == []


def test_build_screen_runs_all_one_or_filtered_tests(relay):
    window = opened(relay, "build")
    assert nodes(relay, window)["test_one"]["wrap"]["kind"] == "unavailable"  # 流す試験を、まだ書いていない
    press(relay, window, "test")
    assert last(relay) == ("test", {})
    assert nodes(relay, window)["out"]["props"]["lines"] == ["2 passed"]
    press(relay, window, "test_name", "changed", text="tests/test_app.py::test_add")
    assert nodes(relay, window)["test_one"]["wrap"] is None
    press(relay, window, "test_one")
    assert last(relay) == ("test", {"tests": ["tests/test_app.py::test_add"]})
    press(relay, window, "filter", "changed", text="login and not slow")
    press(relay, window, "last_failed", "changed", on=True)
    assert nodes(relay, window)["last_failed"]["props"]["on"] is True
    press(relay, window, "test_filtered")
    assert last(relay) == ("test", {"filter": "login and not slow", "last_failed": True})
    assert notices(relay) == []


def test_workspace_stages_unstages_and_discards_the_checked_changes(relay):
    window = opened(relay, "workspace", "C:/work/Calc/.ecobuild/w/12")
    press(relay, window, "changes", "changed", paths=["a.py", "new.txt"])
    press(relay, window, "stage")
    assert ("task add", {"paths": ["a.py", "new.txt"]}) in relay.backend.calls
    relay.input(window, "unstage", "pressed", {}, human=True)
    answer(relay, window, True)  # restore は、確かめてから
    assert ("restore", {"paths": ["a.py", "new.txt"], "staged": True}) in relay.backend.calls
    relay.input(window, "discard", "pressed", {}, human=True)
    answer(relay, window, False)  # いいえ：捨てない
    assert ("restore", {"paths": ["a.py", "new.txt"]}) not in relay.backend.calls
    relay.input(window, "discard", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("restore", {"paths": ["a.py", "new.txt"]}) in relay.backend.calls
    assert relay.display.values(window)["paths"] == []  # 捨てたら、選択を空に
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"


def test_workspace_opens_the_build_and_the_stash_screens_for_the_same_place(relay):
    window = opened(relay, "workspace", "C:/work/Calc/.ecobuild/w/12")
    press(relay, window, "open_build")
    press(relay, window, "open_stashes")
    others = {w["screen"]: w for w in relay.display.windows() if w["id"] != window}
    assert sorted(others) == ["build", "stashes"]
    assert all(w["args"] == {"module": "C:/work/Calc/.ecobuild/w/12"} for w in others.values())

    stashes = others["stashes"]["id"]
    assert nodes(relay, stashes)["list"]["props"]["items"] == ["On task/12-login: 途中の変更", "On main: 試し"]
    press(relay, stashes, "stash")
    assert ("stash", {}) in relay.backend.calls
    press(relay, stashes, "pop")
    assert ("stash pop", {}) in relay.backend.calls
    assert nodes(relay, stashes)["list"]["props"]["items"] == ["On main: 試し"]  # 変えたら読み直す
    relay.input(stashes, "drop", "pressed", {}, human=True)
    assert answer(relay, stashes, True)["part"] == "confirm-box"  # 捨てるのは、確かめてから
    assert ("stash drop", {}) in relay.backend.calls
    assert nodes(relay, stashes)["list"]["props"]["items"] == []
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"


def test_files_screen_works_on_a_folder_and_on_the_checked_files(relay):
    window = opened(relay, "files")
    press(relay, window, "tree", "selected", path="src/util")  # フォルダーを選ぶ
    assert nodes(relay, window)["selected"]["props"]["text"] == "src/util"
    press(relay, window, "destination", "changed", text="src/tools")
    press(relay, window, "move")
    assert ("file move", {"source": "src/util", "destination": "src/tools"}) in relay.backend.calls
    press(relay, window, "tree", "selected", path="src/util")
    relay.input(window, "remove", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("file remove", {"paths": ["src/util"]}) in relay.backend.calls

    press(relay, window, "tree", "changed", paths=["README.md", "src/app.py"])  # いくつもチェックする
    assert nodes(relay, window)["tree"]["props"]["checked"] == ["README.md", "src/app.py"]
    relay.input(window, "restore_checked", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("restore", {"paths": ["README.md", "src/app.py"]}) in relay.backend.calls
    assert nodes(relay, window)["tree"]["props"]["checked"] == []  # 済んだら、チェックを外す
    press(relay, window, "tree", "changed", paths=["README.md", "src/app.py"])
    relay.input(window, "remove_checked", "pressed", {}, human=True)
    answer(relay, window, True)  # 消すのは、確かめてから（1回で全部）
    assert ("file remove", {"paths": ["README.md", "src/app.py"]}) in relay.backend.calls
    press(relay, window, "tree", "changed", paths=["README.md"])
    press(relay, window, "uncheck")
    assert nodes(relay, window)["tree"]["props"]["checked"] == []


def test_files_screen_discards_ignores_and_makes_a_test_for_the_selected_file(relay):
    window = opened(relay, "files")
    view = nodes(relay, window)
    assert all(view[name]["wrap"]["kind"] == "unavailable" for name in ("restore", "ignore_file", "make_test", "do_ignore"))  # まだ選んでいない
    press(relay, window, "tree", "selected", path="src/app.py")
    relay.input(window, "restore", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("restore", {"paths": ["src/app.py"]}) in relay.backend.calls
    press(relay, window, "ignore_file")
    assert ("ignore", {"patterns": ["src/app.py"]}) in relay.backend.calls
    press(relay, window, "pattern", "changed", text="*.log")
    press(relay, window, "do_ignore")
    assert ("ignore", {"patterns": ["*.log"]}) in relay.backend.calls
    press(relay, window, "make_test")
    assert ("file test", {"path": "src/app.py"}) in relay.backend.calls
    assert notices(relay) == []


def test_files_screen_opens_the_record_of_the_selected_file(relay):
    window = opened(relay, "files")
    press(relay, window, "tree", "selected", path="src/app.py")
    press(relay, window, "blame")
    blame = next(w for w in relay.display.windows() if w["screen"] == "blame")
    assert blame["args"] == {"module": "C:/work/Calc", "path": "src/app.py"}
    view = nodes(relay, blame["id"])
    assert view["title"]["props"]["text"] == "src/app.py"
    assert view["lines"]["props"]["text"].endswith("src/app.py の1行目") and ("blame", {"path": "src/app.py"}) in relay.backend.calls
    assert view["log"]["props"]["rows"][0]["sha"] == "abc" and ("log", {"paths": ["src/app.py"], "count": 30}) in relay.backend.calls
    assert relay.backend.modules[-1] == "C:/work/Calc"


def test_cpp_screen_works_on_subprojects(relay):
    files = opened(relay, "files", "C:/work/Game")
    press(relay, files, "to_cpp")  # 同じ窓で切り替わる
    assert [(w["id"], w["screen"], w["args"]) for w in relay.display.windows()] == [(files, "cpp", {"module": "C:/work/Game"})]
    window = files
    view = nodes(relay, window)
    assert view["settings"]["props"]["data"]["main_project"] == "Calc"
    assert [row["name"] for row in view["projects"]["props"]["rows"]] == ["Calc", "CalcTest"]
    assert view["do_project_move"]["wrap"]["kind"] == "unavailable"  # まだ選んでいない

    press(relay, window, "projects", "action", id="Calc", action="choose")
    assert nodes(relay, window)["project_chosen"]["props"]["text"] == "Calc"
    press(relay, window, "project_destination", "changed", text="libs/Calc")
    press(relay, window, "do_project_move")
    assert ("project move", {"name": "Calc", "destination": "libs/Calc"}) in relay.backend.calls
    press(relay, window, "project_name", "changed", text="Math")
    press(relay, window, "do_project_add")
    assert ("project add", {"name": "Math"}) in relay.backend.calls  # 種類（任意）は、決めなければ渡さない
    press(relay, window, "project_kind", "changed", value="app")
    press(relay, window, "do_project_add")
    assert ("project add", {"name": "Math", "kind": "app"}) in relay.backend.calls
    press(relay, window, "update")
    assert ("project update", {}) in relay.backend.calls
    relay.input(window, "projects", "action", {"id": "CalcTest", "action": "remove"}, human=True)
    answer(relay, window, False)  # いいえ：外さない
    assert ("project remove", {"name": "CalcTest"}) not in relay.backend.calls
    relay.input(window, "projects", "action", {"id": "CalcTest", "action": "remove"}, human=True)
    answer(relay, window, True)
    assert ("project remove", {"name": "CalcTest"}) in relay.backend.calls
    assert relay.backend.modules[-1] == "C:/work/Game"
    press(relay, window, "to_files")
    assert relay.display.tree(window)["screen"] == "files"


def test_cpp_screen_works_on_dependencies_and_templates(relay):
    window = opened(relay, "cpp", "C:/work/Game")
    view = nodes(relay, window)
    assert view["deps"]["props"]["rows"][0]["name"] == "Math"
    assert sorted(view["templates"]["props"]["entries"]) == ["header", "widget"]

    press(relay, window, "deps", "action", id="Math", action="update")
    assert ("deps update", {"name": "Math"}) in relay.backend.calls
    press(relay, window, "deps_update")
    assert ("deps update", {}) in relay.backend.calls
    press(relay, window, "deps_sync")
    assert ("deps sync", {}) in relay.backend.calls
    press(relay, window, "deps", "action", id="Math", action="remove")
    assert ("deps remove", {"name": "Math"}) in relay.backend.calls
    press(relay, window, "dep_repository", "changed", text="octocat/Geometry")
    press(relay, window, "do_dep_add")
    assert ("deps add", {"repository": "octocat/Geometry"}) in relay.backend.calls
    press(relay, window, "dep_at", "changed", text="v1.2.0")
    press(relay, window, "do_dep_add")
    assert ("deps add", {"repository": "octocat/Geometry", "at": "v1.2.0"}) in relay.backend.calls

    press(relay, window, "template_name", "changed", text="panel")
    press(relay, window, "template_source", "changed", text="templates/panel.h")
    press(relay, window, "do_template_add")
    assert ("template add", {"name": "panel", "source": "templates/panel.h"}) in relay.backend.calls
    press(relay, window, "templates", "action", id="widget", action="remove")
    assert ("template remove", {"name": "widget"}) in relay.backend.calls
    assert notices(relay) == []
