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
            "task prune": {**spec("change", number={"type": "integer"}), "dry_run": True},  # 本物と同じく、下見（--dry-run）ができる
            "task push": spec("change", force=flag),
            "show": spec("read", commit=text, gui=flag),
            "diff": spec("read", paths=many, staged=flag, base=flag, gui=flag),
            "file test": spec("change", ["path"], path=text, to=text),
            "module settings": spec("read"),
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


def test_workspace_stages_unstages_and_discards_the_checked_changes(relay):
    window = opened(relay, "workspace", "C:/work/Calc/.ecobuild/w/12")
    press(relay, window, "changes", "changed", paths=["a.py", "new.txt"])
    press(relay, window, "changes", "action", name="stage", paths=["a.py", "new.txt"])
    assert ("task add", {"paths": ["a.py", "new.txt"]}) in relay.backend.calls
    relay.input(window, "changes", "action", {"name": "unstage", "paths": ["a.py", "new.txt"]}, human=True)
    relay.idle()  # 入力の窓が確認を兼ねる（もう一度は確かめない）
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
    assert nodes(relay, stashes)["list"]["props"]["stashes"] == ["On task/12-login: 途中の変更", "On main: 試し"]
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"  # 窓の中の操作の試験は test_eco_gui_old.py


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


