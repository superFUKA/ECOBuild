"""エージェントのツール（ecobuild_agent.mcp）：CLI の「エージェントに許す」の印（AGENT）から、MCP のツールを作る。"""

import fnmatch
import io
import json
import os
import sys
import types
from pathlib import Path

import click
import pytest

from ecobuild import config
from ecobuild_agent import mcp
from ecobuild_cli import _catalog, _effects, build_cli
from ecoagent.mcp import ToolError

TYPES = ("cpp", "python", "generic")


@pytest.fixture(scope="module")
def catalog(tmp_path_factory):
    """モジュールの外での ecobuild --help --json の一覧（共通のコマンドと、全部の型のコマンド）。"""
    before = os.getcwd()
    os.chdir(tmp_path_factory.mktemp("outside"))
    try:
        return _catalog.catalog(build_cli, {})
    finally:
        os.chdir(before)


def _typed(catalog, module_type):
    return {**catalog, "type": module_type}


def _all_nodes(nodes):
    for node in nodes:
        yield node
        yield from _all_nodes(node.get("commands", []))


def _context(kind=mcp.OWNER):
    return mcp.Context("a1", "worker", kind, Path("."))


def _names(catalog, module_type, kind=mcp.OWNER, allows=lambda registration, name: True):
    return {tool.name for tool in mcp.tools(_context(kind), _typed(catalog, module_type), lambda argv: {}, allows)}


def test_catalog_has_the_type_and_the_names_of_the_parameters(catalog, tmp_path, monkeypatch):
    assert catalog["type"] is None                        # モジュールの外
    nodes = {n["path"]: n for n in _all_nodes(catalog["commands"])}
    status = nodes["task status"]
    assert status["agent"] == "read" and nodes["task list"]["effect"] == "read"
    assert [a["param"] for a in status["arguments"]] == ["number"]
    assert {o["names"][0]: o["param"] for o in status["options"]}["--issue"] == "issue"
    assert nodes["sync"]["agent"] == "owner"              # グループそのものが実行できるもの（__init__.py の印）
    assert nodes["task start"]["agent"] is None           # 印のないものはツールにしない
    assert "agent" not in nodes["task"]                    # 実行できないグループ
    config_file = tmp_path / config.FILE_NAME
    config_file.parent.mkdir(parents=True)
    config_file.write_text('format = 1\n\n[module]\nname = "M"\ntype = "python"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert _catalog.catalog(build_cli, {})["type"] == "python"


def test_marks_are_one_of_the_three(catalog):
    nodes = list(_all_nodes(catalog["commands"]))
    for entry in catalog["types"].values():
        nodes += list(_all_nodes(entry["commands"]))
    marks = {n.get("agent") for n in nodes if n.get("runnable")}
    assert marks <= {None, *_catalog.AGENT_MARKS} and set(_catalog.AGENT_MARKS) <= marks
    assert set(_catalog.AGENT_MARKS) == set(mcp.MARKS)


@pytest.mark.parametrize("module_type", TYPES)
def test_every_marked_command_has_a_schema_without_json_or_directory(catalog, module_type):
    nodes = mcp.command_nodes(_typed(catalog, module_type))
    assert nodes
    for node in nodes:
        schema = mcp.input_schema(node)
        assert schema["type"] == "object"
        assert not {"json", "yes", "directory", "C"} & set(schema["properties"]), node["path"]
        assert set(schema.get("required", [])) <= set(schema["properties"])
        for prop in schema["properties"].values():
            assert prop["type"] in ("string", "integer", "number", "boolean", "array")


def _sample(item, index):
    """入力の見本の値（既定と違うもの）。位置引数の文字は - で始めて、-- を入れることも確かめる。"""
    kind = item["type"]
    if kind == "bool":
        return not bool(item.get("default"))
    if kind == "int":
        value = 3 + index
    elif kind == "float":
        value = 1.5 + index
    else:
        value = f"-v{index}" if item["kind"] == "argument" else f"値{index}"
    return [value, value] if item.get("multiple") else value


def _runnable(module_type, path):
    cli = build_cli(module_type)
    command, ctx = cli, click.Context(cli, info_name="ecobuild")
    for name in path.split():
        command = command.get_command(ctx, name)
        ctx = click.Context(command, info_name=name, parent=ctx)
    if isinstance(command, click.Group):
        command = command.default_command._load()
    return command


@pytest.mark.parametrize("module_type", TYPES)
def test_schema_to_argv_to_click_gives_back_the_values(catalog, module_type):
    """入力 → argv → click で読むと、元の値に戻る（どの印の付いたコマンドも）。"""
    for node in mcp.command_nodes(_typed(catalog, module_type)):
        arguments = {}
        for index, item in enumerate(mcp._inputs(node)):
            if item["type"] == "bool" and item.get("default") and not item.get("negative"):
                continue                                  # 既定が真で否定形がない：変えられない
            arguments[item["param"]] = _sample(item, index)
        argv = mcp.to_argv(node, arguments)
        assert "--json" in argv
        command = _runnable(module_type, node["path"])
        ctx = command.make_context(node["path"].split()[-1], list(argv), resilient_parsing=False)
        for param, value in arguments.items():
            parsed = ctx.params[param]
            expected = tuple(value) if isinstance(value, list) else value
            if isinstance(parsed, tuple) and not isinstance(expected, tuple):
                expected = (expected,)                     # 0〜1 個の位置引数（可変長で受ける）
            assert parsed == expected, (node["path"], param, argv)


def test_argv_puts_options_first_and_adds_yes_for_confirmation():
    node = {"path": "x remove", "arguments": [{"name": "NAME", "param": "name", "required": True, "multiple": True,
                                               "type": "str"}],
            "options": [{"names": ["--yes", "-y"], "param": "yes", "flag": True, "type": "bool", "default": False},
                        {"names": ["--count"], "param": "count", "flag": False, "type": "int", "default": None},
                        {"names": ["--check"], "param": "check", "flag": True, "type": "bool", "default": True,
                         "negative": "--no-check"}]}
    assert mcp.to_argv(node, {"name": ["a", "b"], "count": 2, "check": False}) == \
        ["--count", "2", "--no-check", "--json", "--yes", "a", "b"]
    assert mcp.to_argv(node, {"name": ["-a"], "check": True}) == ["--json", "--yes", "--", "-a"]
    assert "yes" not in mcp.input_schema(node)["properties"]
    with pytest.raises(ToolError):
        mcp.to_argv(node, {"count": 1})                   # 要る引数がない
    with pytest.raises(ToolError):
        mcp.to_argv(node, {"name": ["a"], "yes": True})   # 知らない入力
    with pytest.raises(ToolError):
        mcp.to_argv(node, {"name": "a"})                  # 配列でない
    with pytest.raises(ToolError):
        mcp.to_argv(node, {"name": ["a"], "count": "2"})  # 型が違う


def test_tools_are_the_common_ones_and_those_of_the_type(catalog):
    python = _names(catalog, "python")
    cpp = _names(catalog, "cpp")
    outside = _names(catalog, None)
    assert {"task_status", "task_list", "status", "check", "build", "test", "file_add"} <= python
    assert "project_list" in cpp and "project_list" not in python
    assert "build" not in outside and "task_status" in outside
    assert not {"task_start", "task_finish", "agent_start", "init"} & cpp


def test_helpers_do_not_get_the_owners_tools(catalog):
    owner = _names(catalog, "python")
    helper = _names(catalog, "python", mcp.HELPER)
    assert {"task_commit", "task_push", "task_submit", "sync"} <= owner
    assert not {"task_commit", "task_push", "task_submit", "sync"} & helper
    assert {"task_status", "build"} <= helper


def test_registration_narrows_the_tools_and_providers_add_some(catalog, monkeypatch):
    monkeypatch.setattr(mcp, "_providers", [])
    seen = []

    @mcp.register_provider
    def children(context):
        seen.append(context)
        return [mcp.Tool("children_list", "子の一覧", {"type": "object", "properties": {}}, lambda a: {"ok": True})]

    names = _names(catalog, "python", allows=lambda registration, name: name.startswith(("task_", "children_")))
    assert "children_list" in names and "build" not in names and "task_status" in names
    assert seen[0].agent_id == "a1" and seen[0].registration == "worker"
    assert not _names(catalog, "python", allows=lambda registration, name: False)


def test_a_tool_runs_the_command_in_the_workspace(catalog):
    calls = []

    def run(argv):
        calls.append(argv)
        return {"ok": True, "result": {"number": 12}}

    tools = {t.name: t for t in mcp.tools(_context(), _typed(catalog, "python"), run, lambda r, n: True)}
    assert tools["task_status"].call({"number": 12}) == {"ok": True, "result": {"number": 12}}
    assert calls == [["task", "status", "--json", "12"]]
    assert tools["build"].call({}) == {"ok": True, "result": {"number": 12}}
    assert calls[-1] == ["build", "--json"]


def test_runner_reads_the_last_json_document(tmp_path):
    script = tmp_path / "fake.py"
    script.write_text("import sys, json\nprint('ログ')\nprint(json.dumps({'ok': True, 'result': sys.argv[1:]}))\n",
                      encoding="utf-8")
    run = mcp.runner([sys.executable, str(script)], tmp_path)
    assert run(["status"]) == {"ok": True, "result": ["-C", str(tmp_path), "status"]}
    broken = tmp_path / "broken.py"
    broken.write_text("import sys\nsys.stderr.write('こわれた')\nsys.exit(3)\n", encoding="utf-8")
    found = mcp.runner([sys.executable, str(broken)], tmp_path)(["status"])
    assert found["ok"] is False and found["error"]["message"] == "こわれた" and found["exit_code"] == 3


def test_agent_mcp_is_hidden_and_for_the_launcher_only():
    cli = build_cli(None)
    command = cli.commands["agent"].commands["mcp"]
    assert command.hidden and _effects.effect("agent mcp") == "human"
    help_text = cli.commands["agent"].get_help(click.Context(cli.commands["agent"], info_name="agent"))
    assert " mcp " not in help_text


def test_agent_mcp_lists_the_tools_over_stdio(tmp_path, monkeypatch, capsys):
    """ecobuild agent mcp：initialize・tools/list に答える（登録は registry の口で読む）。"""
    config_file = tmp_path / config.FILE_NAME
    config_file.parent.mkdir(parents=True)
    config_file.write_text('format = 1\n\n[module]\nname = "M"\ntype = "python"\n', encoding="utf-8")
    registry = types.ModuleType("ecobuild_agent.registry")
    registry.load = lambda name: types.SimpleNamespace(name=name, tools=("task_*", "build"))
    registry.allows_tool = lambda registration, name: any(
        fnmatch.fnmatchcase(name, pattern) for pattern in registration.tools)
    monkeypatch.setitem(sys.modules, "ecobuild_agent.registry", registry)
    monkeypatch.setattr("ecobuild_agent.registry", registry, raising=False)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(p for p in sys.path if p))
    requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(json.dumps(r) + "\n" for r in requests)))
    from ecobuild_cli import main
    with pytest.raises(SystemExit) as stop:
        main(["agent", "mcp", "--agent", "a1", "--registration", "worker", "--kind", "helper",
              "--workspace", str(tmp_path)])
    assert stop.value.code == 0
    answers = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert answers[0]["result"]["serverInfo"]["name"] == "ecobuild-agent"
    names = {t["name"] for t in answers[1]["result"]["tools"]}
    assert {"task_status", "task_list", "build"} <= names
    assert not {"task_commit", "task_submit", "status", "test"} & names     # 手伝い・登録で許していない


def test_agent_mcp_needs_the_agent_and_a_known_kind(capsys):
    from ecobuild_cli import main
    with pytest.raises(SystemExit) as stop:
        main(["agent", "mcp", "--registration", "worker"])
    assert stop.value.code == 2
    with pytest.raises(SystemExit) as stop:
        main(["agent", "mcp", "--agent", "a1", "--registration", "worker", "--kind", "boss"])
    assert stop.value.code == 2
