"""コマンドの重さ（_effects）と、シェルの関所（agent guard）。オペレーターは GUI の側（gui/tests/test_operator.py）。"""

import json

import pytest
from click.testing import CliRunner

from ecobuild_cli import _catalog, _effects, build_cli


def _paths(nodes):
    for node in nodes:
        if node.get("runnable"):
            yield node["path"]
        yield from _paths(node.get("commands", []))


def test_every_listed_effect_names_a_command(tmp_path, monkeypatch):
    """重さの表に書いた名前が、今あるコマンド（共通か型の）であること（名前を変えたら表も直す）。"""
    monkeypatch.chdir(tmp_path)
    catalog = _catalog.catalog(build_cli, {})
    paths = set(_paths(catalog["commands"]))
    for entry in catalog["types"].values():
        paths |= set(_paths(entry["commands"]))
    listed = {path for group in _effects.EFFECTS.values() for path in group} | set(_effects.OVERRIDES)
    assert listed - paths == set()


@pytest.mark.parametrize("args, expected", [
    (["status", "--json"], ("read", "status")),
    (["-C", "C:/Calc", "task", "list"], ("read", "task list")),
    (["--directory=C:/Calc", "task", "start", "12"], ("change", "task start")),
    (["task", "finish", "12"], ("confirm", "task finish")),
    (["workspace", "close", "C:/x"], ("confirm", "workspace close")),
    (["task", "push", "--force"], ("confirm", "task push")),
    (["track", "add", "*.md"], ("change", "track add")),
    (["container", "dockerfile", "--json"], ("read", "container dockerfile")),
    (["container", "dockerfile", "--write", "-"], ("change", "container dockerfile")),   # 環境の Dockerfile を書く
    (["module", "delete", "--help"], ("read", "help")),
    (["setup"], ("human", "setup")),
    (["agent", "guard"], ("human", "agent guard")),
])
def test_classify(args, expected):
    assert _effects.classify(args) == expected


def test_catalog_shows_the_effect(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    nodes = {n["path"]: n for n in _catalog.catalog(build_cli, {})["commands"]}
    task = {c["name"]: c for c in nodes["task"]["commands"]}
    assert task["list"]["effect"] == "read" and task["finish"]["effect"] == "confirm"
    assert "effect" not in nodes["task"]


def test_the_operator_left_the_cli():
    """オペレーター（agent operator・ask・context）は GUI の側（ecobuild gui operator・gui ask）へ移った。"""
    commands = {c.name for c in build_cli(None).commands["agent"].commands.values()}
    assert not {"operator", "ask", "context"} & commands


def test_guard_command():
    def hook(command):
        return CliRunner().invoke(build_cli(None), ["agent", "guard"],
                                  input=json.dumps({"tool_input": {"command": command}}))

    assert hook("ecobuild -C C:/Calc task list --json").exit_code == 0
    stopped = hook("ecobuild task finish 12 --yes")
    assert stopped.exit_code == 2 and "task finish" in stopped.output
    assert hook("git push --force").exit_code == 2


def test_extensions_name_their_effects(tmp_path):
    """拡張は --help --json の actions に {name, effect} を書いて重さを名乗る。名乗っていない呼び方は確認が要る。"""
    from ecobuild_cli import _extensions
    script = tmp_path / "ecobuild-box.py"
    script.write_text("import json\nprint(json.dumps({'ok': True, 'result': {'actions': ["
                      "{'name': 'peek', 'effect': 'read'}, {'name': 'send', 'effect': 'confirm'}, {'name': 'odd', 'effect': 'x'}]}}))\n",
                      encoding="utf-8")
    found = _extensions.effects("box", str(script))
    assert found == {"box peek": "read", "box send": "confirm"}
    assert _effects.classify(["box", "peek"], found) == ("read", "box peek")
    assert _effects.classify(["box", "send", "--text", "hi"], found) == ("confirm", "box send")
    assert _effects.classify(["box", "-C", "x", "module", "delete"], found)[0] == "confirm"
    assert _effects.classify(["status"], found) == ("read", "status")
    assert _extensions.effects("none", str(tmp_path / "missing.exe")) == {}


def test_sending_text_needs_the_users_request():
    """[頼まれたら]：ほかのエージェントへ文字を送るのは、ユーザーが直前の発言で頼んだときだけ。"""
    from ecoagent import guard
    policy = guard.Policy(frozenset({"ecobuild"}), lambda args: (guard.REQUESTED, " ".join(args)))
    command = 'ecobuild gui agent-send --tab 1 --text "テストを実行して"'
    assert guard.check(command, policy, guard.Exchange(prompt="1番にテストを実行してって送って")) is None
    assert "頼んだときだけ" in guard.check(command, policy, guard.Exchange(prompt="ECOSTL で作業始めて"))

