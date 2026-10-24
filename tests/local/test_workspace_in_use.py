"""使用中の作業空間を守る動き（CLI）：消す・切り替える直前に確かめて止める（workspace_in_use）。ロックはない。"""

import json
import os

import pytest
from helpers import git
from click.testing import CliRunner

from ecobuild import usage
from ecobuild.results import CheckItem, CheckReport
from ecobuild_agent import status as agent_status
from ecobuild_cli import build_cli
from ecowork import github as _github

pytestmark = pytest.mark.local


@pytest.fixture
def cli(module, monkeypatch):
    monkeypatch.setattr(_github, "default", lambda: module.repository.github)
    monkeypatch.chdir(module.root)
    runner = CliRunner()

    def invoke(*args):
        return runner.invoke(build_cli(), list(args), catch_exceptions=False)

    return invoke


def as_json(result):
    return json.loads(result.stdout)


def error_code(result):
    return as_json(result)["error"]["code"]


@pytest.fixture
def parallel(cli, module, monkeypatch):
    """タスク #1 を作業空間（元の clone の中の .ecobuild/w/1）で始める。"""
    from ecobuild.results import PrepareResult
    from ecobuild_cpp.type import CppType
    monkeypatch.setattr(CppType, "prepare", lambda self: PrepareResult((), False))
    assert cli("task", "new", "並行作業").exit_code == 0
    assert cli("task", "start", "1", "--name", "作業").exit_code == 0
    return module.root / ".ecobuild" / "w" / "1"


def agent_in(place):
    """place で動いているエージェント（このプロセスの pid）。止めるには stop を呼ぶ。"""
    from ecobuild_agent import agents
    folder = agent_status.prepare(agents.create(registration="worker", workspace=place).folder, place)
    agent_status.started(folder, os.getpid())
    return lambda: (folder / agent_status.RUNNING).unlink()


def test_no_lock_commands_and_no_lock_in_the_status(cli, module):
    """ロックはなくした：workspace lock／unlock はなく、status・workspace list にも lock は出ない。"""
    assert cli("workspace", "lock").exit_code != 0 and cli("workspace", "unlock").exit_code != 0
    assert "lock" not in as_json(cli("status", "--json"))["result"]
    assert "lock" not in as_json(cli("workspace", "list", "--json"))["result"]["modules"][0]


def test_a_workspace_in_use_refuses_removing_and_closing(cli, module, parallel, monkeypatch):
    """使用中（エージェントが動いている）の作業空間は、タスクブランチと一緒に消す操作・閉じる操作を止める。
    ほかのタスクの作業空間は作れる。"""
    stop = agent_in(parallel)
    monkeypatch.chdir(parallel)
    refused = as_json(cli("task", "drop", "1", "--yes", "--json"))["error"]
    assert refused["code"] == "workspace_in_use" and "エージェント" in refused["details"][0]
    assert "終わってから" in refused["hint"] and "unlock" not in refused["hint"]
    assert error_code(cli("workspace", "close", "--discard-local", "--yes", "--json")) == "workspace_in_use"
    assert error_code(cli("workspace", "close", "--dry-run", "--json")) == "workspace_in_use"
    assert parallel.exists() and module.repository.git.current_branch() == "main"
    monkeypatch.chdir(module.root)
    cli("task", "new", "もう1つ")
    assert cli("task", "start", "2", "--name", "b", "--json").exit_code == 0     # ほかの作業空間は作れる
    stop()
    assert cli("task", "drop", "1", "--yes", "--json").exit_code == 0 and not parallel.exists()


def test_running_commands_make_the_workspace_in_use(cli, module, monkeypatch):
    seen = []

    def check(self, **options):
        seen.append(usage.reasons(self.root))
        return CheckReport((CheckItem("generated", True, ""),))

    monkeypatch.setattr(type(module), "check", check)
    assert cli("check", "--json").exit_code == 0
    assert len(seen[0]) == 1 and "check" in seen[0][0] and usage.reasons(module.root) == []


def test_another_workspace_in_use_stops_deleting_its_task_branch(cli, module, parallel, monkeypatch):
    stop = agent_in(parallel)
    for args in (("task", "drop", "1", "--yes"), ("task", "close", "1", "--yes")):
        refused = as_json(cli(*args, "--json"))["error"]
        assert refused["code"] == "workspace_in_use", args
        assert str(parallel) in refused["details"][0] or parallel.as_posix() in refused["details"][0]
    assert as_json(cli("task", "status", "1", "--json"))["result"]["remote"]       # GitHubのタスクブランチも残っている
    assert git(parallel, "status", "--porcelain").strip() == ""
    stop()
    assert cli("task", "drop", "1", "--yes", "--json").exit_code == 0
