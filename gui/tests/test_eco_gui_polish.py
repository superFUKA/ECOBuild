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
        self.failing = False  # test を失敗させる

    def _specs(self, text):
        many, flag = {"type": "array", "items": text}, {"type": "boolean"}
        build = {"configuration": text, "profile": text, "project": text}
        return {
            **super()._specs(text),
            "profile add": spec("change", ["name"], name=text, configuration=text, parallel={"type": "integer"}, shared=flag),
            "file add": spec("change", paths=many, template=text, test=flag),
            "task commit": spec("change", paths=many, message=text, all=flag, amend=flag),
            "project show": spec("read", projects=text, project=text),
            "project set": spec("change", projects=text, project=text, kind=text, add_define=text, remove_define=text,
                                add_include=text, remove_include=text),
            "project link": spec("change", library=many, project=text, type=text),
            "project unlink": spec("change", ["link"], link=text, project=text),
            "project pch": spec("change", projects=text, project=text, off=flag),
            "deps tree": spec("read"), "deps versions": spec("change", ["name"], name=text, branch=text, count={"type": "integer"}),
            "profile list": spec("read"), "profile use": spec("change", ["name"], name=text), "profile remove": spec("change", ["name"], name=text),
            "build": spec("change", **build), "rebuild": spec("change", **build), "clean": spec("change", **build),
            "run": spec("change", argv=many, arguments=text, **build),
            "test": spec("change", tests=many, filter=text, last_failed=flag, list=flag, **build),
            "stash list": spec("read"), "stash": spec("change"),
            "stash pop": spec("change", number={"type": "integer"}, index={"type": "integer"}),
            "stash drop": spec("confirm", number={"type": "integer"}, index={"type": "integer"}),
            "tests": spec("read", **build),
            "restore": spec("confirm", paths=many, staged=flag, source=text),
            "task add": spec("change", paths=many, all=flag),
            "ignore": spec("change", patterns=many),
            "blame": spec("read", ["path"], path=text, gui=flag),
            "log": spec("read", paths=many, count={"type": "integer"}, branch=text, unpushed=flag),
            # 作業空間の窓が呼ぶもの
            "status": spec("read", fetch=flag), "files": spec("read"), "check": spec("read"),
            "sync": spec("change", from_branch=text, at=text),
            "task reset": spec("confirm", ["commit"], commit=text, keep=flag),
            "task prune": spec("change", number={"type": "integer"}),
            "task push": spec("change", force=flag),
            "show": spec("read", commit=text, gui=flag),
            "diff": spec("read", paths=many, staged=flag, base=flag, gui=flag),
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
        module = str(args.get("module") or "")
        args = {key: value for key, value in args.items() if key != "module"}
        if name == "module show" and module.startswith("C:/work/Game"):  # C++ のモジュール
            return {"ok": True, "result": {**result["result"], "name": "Game", "type": "cpp"}}
        if name in ("build", "rebuild", "clean"):
            return {"ok": True, "result": {"project": args.get("project"), "configuration": args.get("configuration") or "Debug",
                                           "artifacts": [] if name == "clean" else ["dist/calc-1.0-py3-none-any.whl"], "profile": None, "action": name}}
        if name == "run":
            return {"ok": True, "result": {"project": None, "configuration": "Debug", "returncode": 0, "output": "hello"}}
        if name == "test" and self.failing:
            return {"ok": False, "error": {"code": "test_failed", "message": "テストが失敗しました"}}
        if name == "project show":
            return {"ok": True, "result": {"name": args["project"], "kind": "static_library", "directory": args["project"], "main": True,
                                           "source_directories": ["src"], "links": [{"id": "g-1", "kind": "library", "name": "Math", "as": "static"}]}}
        if name == "deps tree":
            return {"ok": True, "result": {"module": "Game", "direct": ["Math"], "nodes": [
                {"name": "Math", "url": "https://example.invalid/Math", "revision": "abc", "present": True, "depends_on": ["Core"]},
                {"name": "Core", "url": "https://example.invalid/Core", "revision": "def", "present": False, "depends_on": []}]}}
        if name == "deps versions":
            return {"ok": True, "result": {"name": args["name"], "url": "https://example.invalid/Math", "recorded": "abc", "default_branch": "main",
                                           "branch": "main", "branches": ["main", "dev"], "tags": [{"name": "v1.2.0", "sha": "abc"}],
                                           "commits": [{"sha": "fff", "date": "2026-11-02", "subject": "新しい", "tags": []},
                                                       {"sha": "abc", "date": "2026-11-01", "subject": "最初", "tags": ["v1.2.0"]}]}}
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
            return {"ok": True, "result": {"project": None, "configuration": "Debug", "passed": 2, "failed": 0, "skipped": 1, "cases": []}}
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
    press(relay, window, "changes", "action", name="stage", paths=["a.py", "new.txt"])
    assert ("task add", {"paths": ["a.py", "new.txt"]}) in relay.backend.calls
    relay.input(window, "changes", "action", {"name": "unstage", "paths": ["a.py", "new.txt"]}, human=True)
    answer(relay, window, True)  # restore は、確かめてから
    assert ("restore", {"paths": ["a.py", "new.txt"], "staged": True}) in relay.backend.calls
    relay.input(window, "changes", "action", {"name": "discard", "paths": ["a.py", "new.txt"]}, human=True)
    answer(relay, window, False)  # いいえ：捨てない
    assert ("restore", {"paths": ["a.py", "new.txt"]}) not in relay.backend.calls
    relay.input(window, "changes", "action", {"name": "discard", "paths": ["a.py", "new.txt"]}, human=True)
    answer(relay, window, True)
    assert ("restore", {"paths": ["a.py", "new.txt"]}) in relay.backend.calls
    assert relay.display.values(window)["paths"] is None  # 捨てたら、選択を空に（まだ選んでいない）
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"


def test_workspace_opens_the_build_and_the_stash_screens_for_the_same_place(relay):
    window = opened(relay, "workspace", "C:/work/Calc/.ecobuild/w/12")
    press(relay, window, "toolbar", "action", name="build_settings")
    press(relay, window, "changes", "action", name="stash_list")
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
    window = opened(relay, "files", "C:/work/Game")  # 試験を作るのは、C++ のモジュールだけ
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


# --- 仕上げ：型ごとの引数・型での出し分け・チェックが空のときの灰色・実行の結果 -----------------------------------

def test_commands_of_every_module_type_accept_the_arguments_of_any_type():
    from eco_gui.backend import EcobuildBackend

    def option(param, flag=False):
        return {"names": ["--" + param.replace("_", "-")], "param": param, "help": param, "flag": flag, "type": "bool" if flag else "str",
                "negative": None, "required": False, "multiple": False}

    def argument(param, required=False, multiple=False):
        return {"name": param.upper(), "param": param, "help": param, "required": required, "multiple": multiple, "type": "str"}

    def node(path, arguments=(), options=(), effect="change", commands=()):
        return {"name": path.split()[-1], "path": path, "summary": path, "runnable": bool(effect), "effect": effect,
                "arguments": list(arguments), "options": list(options), "commands": list(commands)}

    common = [option("configuration"), option("json", True)]
    catalog = {"ok": True, "result": {"type": "python", "commands": [node("status", effect="read")], "types": {
        "cpp": {"commands": [
            node("build", [argument("projects")], [option("project"), *common]),
            node("run", [argument("projects")], [option("project"), option("arguments"), *common]),
            node("file", effect=None, commands=[
                node("file add", [argument("paths", multiple=True)], [option("test", True), option("template")]),
                node("file remove", [argument("paths", multiple=True)], effect="human"),
                node("file test", [argument("path", required=True)])]),
            node("profile", effect=None, commands=[node("profile add", [argument("name", required=True)], [option("shared", True)])])]},
        "generic": {"commands": [
            node("build", [], common), node("run", [], [option("arguments"), *common]),
            node("file", effect=None, commands=[node("file add", [argument("paths", multiple=True)]),
                                                node("file remove", [argument("paths", multiple=True)], effect="change")]),
            node("profile", effect=None, commands=[node("profile add", [argument("name", required=True)])])]},
        "python": {"commands": [
            node("build", [], common), node("run", [argument("argv", multiple=True)], [option("arguments"), option("stdin", True), *common]),
            node("file", effect=None, commands=[node("file add", [argument("paths", multiple=True)], [option("test", True)])]),
            node("profile", effect=None, commands=[node("profile add", [argument("name", required=True)], [option("parallel")])])]},
    }}}
    backend = EcobuildBackend(["ecobuild"])
    backend.ask = lambda argv: catalog
    specs = backend.commands()
    assert sorted(specs) == ["build", "file add", "file remove", "file test", "profile add", "run", "status"]  # 同じ名前は1つ
    # どれかの型が受ける引数は、書ける
    assert sorted(specs["build"]["args"]["properties"]) == ["configuration", "module", "project", "projects"]
    assert sorted(specs["run"]["args"]["properties"]) == ["arguments", "argv", "configuration", "module", "project", "projects", "stdin"]
    assert sorted(specs["file add"]["args"]["properties"]) == ["module", "paths", "template", "test"]
    assert sorted(specs["profile add"]["args"]["properties"]) == ["module", "name", "parallel", "shared"]
    assert specs["profile add"]["args"]["required"] == ["name"]  # どの型でも必須のものだけが必須
    assert specs["build"]["args"]["required"] == [] and specs["file test"]["args"]["required"] == ["path"]
    assert specs["file remove"]["weight"] == "confirm"  # 重さが型で違えば、重い方
    # C++ だけのオプションが、コマンドラインになる（受けない型のモジュールでは、ecobuild が断る）
    assert backend.command_line("build", {"module": "C:/m", "project": "Calc", "configuration": "Release"}) == [
        "ecobuild", "-C", "C:/m", "build", "--project", "Calc", "--configuration", "Release", "--json"]
    assert backend.command_line("file add", {"paths": ["a.h"], "template": "header"}) == [
        "ecobuild", "file", "add", "--template", "header", "--json", "--", "a.h"]
    assert backend.command_line("run", {"argv": ["--port", "80"]}) == ["ecobuild", "run", "--json", "--", "--port", "80"]
    assert backend.command_line("build", {}) == ["ecobuild", "build", "--json"]  # 渡さなければ、今までどおり


def test_files_screen_shows_the_cpp_parts_only_in_a_cpp_module(relay):
    python = opened(relay, "files", "C:/work/Calc")
    view = nodes(relay, python)
    assert relay.display.values(python)["module_type"] == "python"
    assert all(view[name]["wrap"]["kind"] == "hidden" for name in ("to_cpp", "make_test", "template"))
    with pytest.raises(Exception):  # 隠した部品は、入力も受けない
        relay.input(python, "to_cpp", "pressed", {}, human=True)
    press(relay, python, "new_path", "changed", text="src/util.py")
    press(relay, python, "do_add")
    assert last(relay) == ("file add", {"paths": ["src/util.py"]})

    cpp = opened(relay, "files", "C:/work/Game")
    view = nodes(relay, cpp)
    assert relay.display.values(cpp)["module_type"] == "cpp"
    assert all((view[name]["wrap"] or {}).get("kind") != "hidden" for name in ("to_cpp", "make_test", "template"))
    press(relay, cpp, "new_path", "changed", text="Calc/include/Calc/Shape.h")
    press(relay, cpp, "do_add")
    assert last(relay) == ("file add", {"paths": ["Calc/include/Calc/Shape.h"]})  # テンプレートは、書かなければ渡さない
    press(relay, cpp, "template", "changed", text="header")
    press(relay, cpp, "do_add")
    assert last(relay) == ("file add", {"paths": ["Calc/include/Calc/Shape.h"], "template": "header"})
    assert relay.backend.modules[-1] == "C:/work/Game" and notices(relay) == []


def test_files_screen_greys_the_buttons_for_the_checked_files_while_nothing_is_checked(relay):
    window = opened(relay, "files")
    many = ("remove_checked", "restore_checked")
    assert all(nodes(relay, window)[name]["wrap"]["kind"] == "unavailable" for name in many)  # まだ1つもチェックしていない
    press(relay, window, "tree", "changed", paths=["README.md"])
    assert all(nodes(relay, window)[name]["wrap"] is None for name in many)
    press(relay, window, "tree", "changed", paths=None)  # チェックを全部外すと、部品は null を出す
    view = nodes(relay, window)
    assert view["tree"]["props"]["checked"] == [] and all(view[name]["wrap"]["kind"] == "unavailable" for name in many)
    press(relay, window, "tree", "changed", paths=["README.md"])
    press(relay, window, "uncheck")
    assert all(nodes(relay, window)[name]["wrap"]["kind"] == "unavailable" for name in many)
    press(relay, window, "tree", "changed", paths=["README.md"])
    relay.input(window, "remove_checked", "pressed", {}, human=True)
    answer(relay, window, True)
    assert last(relay) == ("file remove", {"paths": ["README.md"]})
    assert all(nodes(relay, window)[name]["wrap"]["kind"] == "unavailable" for name in many)  # 済んだら、また灰色
    assert not [call for call in relay.backend.calls if call[0] in ("file remove", "restore") and not call[1].get("paths")]


def test_workspace_tells_the_parts_what_is_checked(relay):
    """チェックしたファイルは、変更の一覧とコミットの欄へ出る（ボタンを押せるかは、その部品が見せる）。"""
    window = opened(relay, "workspace", "C:/work/Calc/.ecobuild/w/12")
    view = nodes(relay, window)
    assert view["changes"]["props"]["none_when_empty"] is True and view["changes"]["props"]["tools"] is True
    assert view["changes"]["props"]["checked"] == [] and view["commit_box"]["props"]["checked"] is None
    press(relay, window, "changes", "changed", paths=["a.py"])
    view = nodes(relay, window)
    assert view["changes"]["props"]["checked"] == ["a.py"] and view["commit_box"]["props"]["checked"] == ["a.py"]
    press(relay, window, "changes", "changed", paths=None)  # チェックを全部外した
    view = nodes(relay, window)
    assert view["changes"]["props"]["checked"] == [] and view["commit_box"]["props"]["checked"] is None


def test_workspace_amends_the_last_commit_and_restores_from_another_commit(relay):
    window = opened(relay, "workspace", "C:/work/Calc/.ecobuild/w/12")
    press(relay, window, "changes", "changed", paths=["a.py"])
    press(relay, window, "commit_box", "changed", text="直す")
    press(relay, window, "commit_box", "amend", on=True)
    assert nodes(relay, window)["commit_box"]["props"]["amend"] is True
    press(relay, window, "commit_box", "commit")
    assert last(relay) == ("task commit", {"paths": ["a.py"], "message": "直す", "amend": True})
    values = relay.display.values(window)
    assert values["amend"] is None and values["message"] is None  # 1回ごとに外す。メッセージも空に戻す
    assert nodes(relay, window)["commit_box"]["props"]["amend"] is None and nodes(relay, window)["commit_box"]["props"]["text"] is None
    press(relay, window, "changes", "changed", paths=["b.py"])
    press(relay, window, "commit_box", "changed", text="もう1つ直す")
    press(relay, window, "commit_box", "commit")
    assert last(relay) == ("task commit", {"paths": ["b.py"], "message": "もう1つ直す"})
    # 別のコミットの状態へ戻す（ecobuild restore --source <コミット>）は、ログのコミットのメニューから
    press(relay, window, "tabs", "selected", tab="log")
    relay.input(window, "log:list", "action", {"name": "restore", "sha": "abc"}, human=True)
    answer(relay, window, True)
    relay.idle()
    assert last(relay) == ("restore", {"source": "abc"})


def test_build_screen_shows_the_result_of_the_last_successful_run(relay):
    window = opened(relay, "build")
    results = ("build_facts", "artifacts", "test_facts", "run_facts")

    def shown():
        view = nodes(relay, window)
        return [name for name in results if (view[name]["wrap"] or {}).get("kind") != "hidden"]

    assert shown() == []  # まだ何も実行していない
    press(relay, window, "build")
    view = nodes(relay, window)
    assert shown() == ["build_facts", "artifacts"]
    assert view["artifacts"]["props"]["items"] == ["dist/calc-1.0-py3-none-any.whl"]  # ビルドの成果物
    assert view["build_facts"]["props"]["data"]["action"] == "build" and view["build_facts"]["props"]["data"]["configuration"] == "Debug"
    press(relay, window, "test")
    view = nodes(relay, window)
    assert shown() == ["test_facts"]
    assert [view["test_facts"]["props"]["data"][key] for key in ("passed", "failed", "skipped")] == [2, 0, 1]  # 試験の成功・失敗の数
    press(relay, window, "run")
    assert shown() == ["run_facts"] and nodes(relay, window)["run_facts"]["props"]["data"]["returncode"] == 0  # 終了コード
    press(relay, window, "clean")
    view = nodes(relay, window)
    assert shown() == ["build_facts", "artifacts"] and view["artifacts"]["props"]["items"] == [] and view["build_facts"]["props"]["data"]["action"] == "clean"
    assert notices(relay) == []
    relay.backend.failing = True  # 失敗したら、結果は変えない（失敗は知らせで出る）
    press(relay, window, "test")
    assert shown() == ["build_facts", "artifacts"] and notices(relay) == ["テストが失敗しました"]


def test_build_screen_adds_a_profile_and_shows_the_cpp_fields_only_in_a_cpp_module(relay):
    python = opened(relay, "build", "C:/work/Calc")
    view = nodes(relay, python)
    assert view["project"]["wrap"]["kind"] == "hidden" and view["profile_shared"]["wrap"]["kind"] == "hidden"
    assert (view["profile_parallel"]["wrap"] or {}).get("kind") != "hidden"
    assert view["do_profile_add"]["wrap"]["kind"] == "unavailable"  # 名前を、まだ書いていない
    press(relay, python, "profile_name", "changed", text="ship")
    press(relay, python, "do_profile_add")
    assert last(relay) == ("profile add", {"name": "ship"})  # 決めていない項目は渡さない（CLI の既定）
    press(relay, python, "profile_configuration", "changed", value="Release")
    press(relay, python, "profile_parallel", "changed", text="8")
    press(relay, python, "do_profile_add")
    assert last(relay) == ("profile add", {"name": "ship", "configuration": "Release", "parallel": 8})  # 数は、コマンドの型で渡る
    press(relay, python, "build")
    assert last(relay) == ("build", {})

    cpp = opened(relay, "build", "C:/work/Game")
    view = nodes(relay, cpp)
    assert all((view[name]["wrap"] or {}).get("kind") != "hidden" for name in ("project", "profile_shared", "profile_parallel"))
    press(relay, cpp, "project", "changed", text="Calc")
    for button in ("build", "rebuild", "clean", "run", "test"):
        press(relay, cpp, button)
        assert last(relay) == (button, {"project": "Calc"})
    assert nodes(relay, cpp)["build_facts"]["props"]["data"]["project"] == "Calc"  # 結果にも、対象が出る
    assert nodes(relay, python)["build_facts"]["props"]["data"]["project"] is None  # 結果は窓ごと
    press(relay, cpp, "profile_name", "changed", text="dll")
    press(relay, cpp, "profile_shared", "changed", on=True)
    press(relay, cpp, "do_profile_add")
    assert last(relay) == ("profile add", {"name": "dll", "shared": True})
    assert relay.backend.modules[-1] == "C:/work/Game" and notices(relay) == []


def test_cpp_screen_shows_and_changes_the_chosen_subproject(relay):
    window = opened(relay, "cpp", "C:/work/Game")
    buttons = ("do_link", "do_set_kind", "add_define", "remove_define", "add_include", "remove_include", "pch_on", "pch_off")
    view = nodes(relay, window)
    assert all(view[name]["wrap"]["kind"] == "unavailable" for name in buttons)  # まだ選んでいない
    assert not [call for call in relay.backend.calls if call[0] == "project show"]  # 選ぶまで読まない
    press(relay, window, "projects", "action", id="Calc", action="choose")
    view = nodes(relay, window)
    assert ("project show", {"project": "Calc"}) in relay.backend.calls
    assert view["detail_chosen"]["props"]["text"] == "Calc" and view["details"]["props"]["data"]["kind"] == "static_library"
    assert [row["name"] for row in view["links"]["props"]["rows"]] == ["Math"]
    assert view["pch_on"]["wrap"] is None and view["do_set_kind"]["wrap"]["kind"] == "unavailable"  # 種類は、まだ選んでいない

    press(relay, window, "links", "action", id="g-1", action="unlink")
    assert last(relay) == ("project unlink", {"link": "g-1", "project": "Calc"})
    press(relay, window, "link_library", "changed", text="Geometry")
    press(relay, window, "do_link")
    assert last(relay) == ("project link", {"library": ["Geometry"], "project": "Calc"})
    press(relay, window, "set_kind", "changed", value="shared")
    press(relay, window, "do_set_kind")
    assert last(relay) == ("project set", {"project": "Calc", "kind": "shared"})
    press(relay, window, "define", "changed", text="USE_FOO,LEVEL=2")
    press(relay, window, "add_define")
    assert last(relay) == ("project set", {"project": "Calc", "add_define": "USE_FOO,LEVEL=2"})
    press(relay, window, "remove_define")
    assert last(relay) == ("project set", {"project": "Calc", "remove_define": "USE_FOO,LEVEL=2"})
    press(relay, window, "include", "changed", text="third_party/include")
    press(relay, window, "add_include")
    assert last(relay) == ("project set", {"project": "Calc", "add_include": "third_party/include"})
    press(relay, window, "remove_include")
    assert last(relay) == ("project set", {"project": "Calc", "remove_include": "third_party/include"})
    press(relay, window, "pch_on")
    assert last(relay) == ("project pch", {"project": "Calc"})
    press(relay, window, "pch_off")
    assert last(relay) == ("project pch", {"project": "Calc", "off": True})
    assert relay.backend.modules[-1] == "C:/work/Game" and notices(relay) == []


def test_cpp_screen_shows_the_dependency_tree_and_picks_a_version(relay):
    window = opened(relay, "cpp", "C:/work/Game")
    view = nodes(relay, window)
    assert [(row["name"], row["depends_on"]) for row in view["dep_tree"]["props"]["rows"]] == [("Math", ["Core"]), ("Core", [])]
    assert view["versions"]["props"]["rows"] == []
    assert not [call for call in relay.backend.calls if call[0] == "deps versions"]  # 押すまで、GitHub から取り込まない
    press(relay, window, "deps", "action", id="Math", action="versions")
    view = nodes(relay, window)
    assert ("deps versions", {"name": "Math"}) in relay.backend.calls
    assert view["versions_title"]["props"]["text"] == "Math" and view["versions_info"]["props"]["data"]["recorded"] == "abc"
    assert [row["sha"] for row in view["versions"]["props"]["rows"]] == ["fff", "abc"]
    press(relay, window, "versions", "action", id="fff", action="use")
    assert last(relay) == ("deps update", {"name": "Math", "at": "fff"})
    assert notices(relay) == []
