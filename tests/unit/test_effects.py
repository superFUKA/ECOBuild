"""コマンドの重さ（_effects）と、シェルの関所（agent guard）。オペレーターは GUI の側（gui/tests/test_operator.py）。"""

import json

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

    stopped = hook("ecobuild -C C:/Calc task list --json")                 # 作業空間のエージェント：ecobuild はツールで
    assert stopped.exit_code == 2 and "MCP のツール" in stopped.output
    assert hook("git push --force").exit_code == 2
    assert hook("git status && ls").exit_code == 0                           # ダメなもの以外は通す
