"""作業空間をコンテナにしていれば、ビルド等をコンテナの中の ecobuild に渡す（ecobuild_cli._inside）。docker は動かさない。"""

import json

import pytest

from ecobuild import config
import ecobuild_bundle  # noqa: F401（コンテナの拡張に型をつなぐ）
import ecobuild_container as container
from ecobuild_cli import _inside


@pytest.fixture
def root(tmp_path, monkeypatch):
    path = tmp_path / "Calc"
    config.save(config.ModuleConfig.for_new_module("Calc", "generic"), path / config.FILE_NAME)
    (path / "src").mkdir()
    monkeypatch.chdir(path / "src")
    monkeypatch.delenv(container.INSIDE, raising=False)
    return path


def test_only_the_tool_commands_of_a_container_workspace(root, monkeypatch):
    calls = []
    monkeypatch.setattr(container, "run_inside", lambda r, args, **kw: calls.append((r, args, kw)) or (0, ""))
    assert _inside.route(["build"], False) is None                     # コンテナにしていない
    config.save_local(root, {container.KEY: True})
    assert _inside.route(["task", "commit"], False) is None            # git の操作はこのPCで
    assert _inside.route(["build", "--help"], False) is None
    assert _inside.route(["test", "--project", "Calc"], False) == 0
    r, args, kw = calls[0]
    assert r == root and args == ["ecobuild", "test", "--project", "Calc"] and kw["cwd"].name == "src"
    monkeypatch.setenv(container.INSIDE, "1")                          # 中の ecobuild はもう渡さない
    assert _inside.route(["build"], False) is None


def test_json_paths_are_read_back_as_this_pc(root, monkeypatch, capsys):
    config.save_local(root, {container.KEY: True})
    out = json.dumps({"ok": True, "module": "/work", "result": {"artifacts": ["/work/build/a.exe", "/workx"]}})
    monkeypatch.setattr(container, "run_inside", lambda r, args, **kw: (1, out + "\n"))
    assert _inside.route(["build", "--json"], True) == 1
    document = json.loads(capsys.readouterr().out)
    assert document["module"] == root.as_posix()
    assert document["result"]["artifacts"] == [root.as_posix() + "/build/a.exe", "/workx"]
