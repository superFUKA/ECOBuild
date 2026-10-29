"""コンテナにした作業空間でも、ビルド等をこのPCで実行する（ecobuild host・container set --host-run on・ツール host_run）。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from ecobuild import config
import ecobuild_bundle  # noqa: F401（コンテナの拡張に型をつなぐ）
import ecobuild_container as container
from ecobuild_agent import children, host, inside, mcp, registry
from ecobuild_agent import serve as agent_serve
from ecobuild_bundle import Module
from ecobuild_cli import _inside, main


@pytest.fixture
def root(tmp_path, monkeypatch):
    path = tmp_path / "Calc"
    config.save(config.ModuleConfig.for_new_module("Calc", "generic"), path / config.FILE_NAME)
    config.save_local(path, {container.KEY: True})
    monkeypatch.chdir(path)
    monkeypatch.delenv(container.INSIDE, raising=False)
    monkeypatch.delenv(container.HOST, raising=False)
    return path


def test_host_runs_the_command_on_this_pc_without_passing_it_inside(root, monkeypatch):
    monkeypatch.setattr(container, "run_inside", lambda *a, **kw: pytest.fail("中へ渡した"))
    seen = []
    monkeypatch.setattr(_inside, "route", lambda args, json_output: seen.append(args) or container.routed(root) or None)
    with pytest.raises(SystemExit):
        main(["host", "clean", "--json"])
    assert seen == [["clean", "--json"]]                     # host を外して、ふつうのコマンドとして
    assert container.routed(root) is False                   # 確認（ContainerModule.check）も中へ渡さない
    monkeypatch.delenv(container.HOST)
    assert container.routed(root) is True


def test_host_without_a_runnable_command_is_a_usage_error(root, capsys):
    for args in (["host"], ["host", "status"]):
        with pytest.raises(SystemExit) as stop:
            main(args)
        assert stop.value.code == 2
    assert "build" in capsys.readouterr().err


def test_host_run_is_kept_on_this_pc_only(root):
    assert inside.host_run(root) is False                    # 既定は許さない
    assert inside.set_host_run(root, True) is True
    assert inside.set_host_run(root, True) is False
    assert inside.host_run(root) and "host_run" not in config.load_local(root)   # 作業空間（中から書ける）には書かない
    assert inside.set_host_run(root, False) is True and not inside.host_run(root)


def test_container_set_turns_host_run_on_and_off(root, monkeypatch, capsys):
    monkeypatch.setattr(container, "configure", lambda r, **kw: container.WorkspaceContainer(
        Path(r), True, False, True, "", container.name(r)))           # docker は動かさない
    with pytest.raises(SystemExit) as stop:
        main(["container", "set", "--host-run", "on"])
    assert stop.value.code == 0 and inside.host_run(root)
    assert "このPCで実行させます" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["container", "set", "--host-run", "off"])
    assert not inside.host_run(root)
    with pytest.raises(SystemExit) as stop:
        main(["container", "set", "--host-run", "yes"])
    assert stop.value.code == 2


def test_the_mcp_server_gets_host_run_only_when_allowed(root):
    record = SimpleNamespace(id="a-0123456789", registration="worker", kind="owner")
    stub = SimpleNamespace(root=root)
    assert "--host-run" not in Module.mcp_config(stub, record)["mcpServers"]["ecobuild"]["args"]
    inside.set_host_run(root, True)
    assert Module.mcp_config(stub, record)["mcpServers"]["ecobuild"]["args"][-1] == "--host-run"
    assert "--host-run" not in Module.mcp_config(stub, record, boxed=False)["mcpServers"]["ecobuild"]["args"]


def test_the_tool_is_given_only_with_host_run():
    registration = registry.Registration(name="worker", title="worker", document="", tools=("*",))
    names = lambda allowed: [t.name for t in host.tools(mcp.Context("a-1", registration, mcp.OWNER, Path("/w"), allowed))]
    assert names(False) == [] and names(True) == [host.TOOL]


def test_check_arguments():
    assert host.check_arguments({"command": "test", "args": ["--filter", "x"]}) == {"command": "test", "args": ["--filter", "x"]}
    assert host.argv({"command": "build", "args": ["--json"]}) == ["host", "build", "--json"]
    for bad in ({"command": "status"}, {"command": "build", "args": "x"}, {"command": "build", "other": 1},
                {"command": "build", "args": ["-C", "/"]}):
        with pytest.raises(Exception):
            host.check_arguments(bad)


def test_serve_runs_it_on_this_pc_only_when_this_pc_allows(root, tmp_path, monkeypatch):
    caller = SimpleNamespace(id="a-0123456789", name="worker", workspace=str(root), registration="worker")
    monkeypatch.setattr(agent_serve.agents, "load", lambda agent_id: caller)
    monkeypatch.setattr(children, "_registration", lambda record: registry.Registration(
        name="worker", title="worker", document="", tools=("*",)))
    ran = []
    serve = agent_serve.Serve(lambda args, cwd, **_: ran.append((args, cwd)) or {"ok": True, "result": {"built": 1}},
                              background=False)
    request = {"tool": host.TOOL, "arguments": {"command": "build"}, "agent": caller.id}
    folder = tmp_path / caller.id
    refused = serve.handle(root, request, folder=folder, human=False)
    assert not refused["ok"] and "許していません" in refused["error"]["message"] and ran == []
    inside.set_host_run(root, True)
    done = serve.handle(root, request, folder=folder, human=False)
    assert done["ok"] and done["result"] == {"ok": True, "result": {"built": 1}}
    assert ran == [(["host", "build", "--json"], Path(root))]
