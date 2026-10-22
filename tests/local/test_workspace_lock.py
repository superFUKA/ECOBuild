"""workspace lock／unlock と、使用中（ロック中）の作業空間を守る動き（CLI）。"""

import json
import os

import pytest
from helpers import git
from click.testing import CliRunner

from ecobuild import locks
from ecobuild.results import CheckItem, CheckReport
from ecobuild_agent import status as agent_status
from ecobuild_cli import build_cli
from ecobuild_container import name as container_name
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


def test_lock_and_unlock_shapes(cli, module):
    result = as_json(cli("workspace", "lock", "--reason", "調査中", "--json"))["result"]
    assert result["path"] == module.root.as_posix() and result["lock"]["locked"] is True
    reason = result["lock"]["reasons"][0]
    assert set(reason) == {"kind", "text", "since", "pid"} and reason["kind"] == "manual" and reason["pid"] is None
    assert "調査中" in reason["text"] and reason["since"]
    # 状態を返すコマンドにも lock がある
    assert as_json(cli("status", "--json"))["result"]["lock"] == result["lock"]
    listed = as_json(cli("workspace", "list", "--json"))["result"]["modules"]
    assert [e["lock"] for e in listed] == [result["lock"]]
    assert "ロック中" in cli("status").output and "調査中" in cli("workspace", "list").output
    unlocked = as_json(cli("workspace", "unlock", "--json"))["result"]
    assert unlocked["lock"] == {"locked": False, "reasons": []}
    assert as_json(cli("status", "--json"))["result"]["lock"]["locked"] is False


def test_locked_workspace_refuses_removing_and_closing(cli, module, monkeypatch):
    """ロック中の作業空間は、タスクブランチと一緒に消す操作・閉じる操作を止める。ほかのタスクの作業空間は作れる。"""
    cli("task", "new", "a")
    cli("task", "new", "b")
    assert cli("task", "start", "1", "--name", "a").exit_code == 0
    work = module.root / ".ecobuild" / "w" / "1"
    monkeypatch.chdir(work)
    cli("workspace", "lock")
    assert cli("task", "start", "1", "--json").exit_code == 0                     # 同じ作業空間を返すだけ
    refused = as_json(cli("task", "drop", "1", "--yes", "--json"))["error"]
    assert refused["code"] == "workspace_locked" and "手動でロック" in refused["details"][0]
    assert "workspace unlock" in refused["hint"] and "--force" not in refused["hint"]
    assert error_code(cli("workspace", "close", "--discard-local", "--yes", "--json")) == "workspace_locked"
    assert error_code(cli("workspace", "close", "--dry-run", "--json")) == "workspace_locked"
    assert work.exists() and module.repository.git.current_branch() == "main"
    assert cli("task", "start", "2", "--name", "b", "--json").exit_code == 0     # ほかの作業空間は作れる
    monkeypatch.chdir(work)
    cli("workspace", "unlock")
    assert cli("task", "drop", "1", "--yes", "--json").exit_code == 0 and not work.exists()


def test_automatic_lock_needs_force(cli, module):
    folder = agent_status.prepare(container_name(module.root), module.root)
    agent_status.started(folder, os.getpid())
    state = as_json(cli("workspace", "unlock", "--json"))["result"]["lock"]            # 普通の unlock では外れない
    assert state["locked"] and state["reasons"][0]["kind"] == "agent" and state["reasons"][0]["pid"] == os.getpid()
    assert error_code(cli("workspace", "unlock", "--force", "--json")) == "confirmation_required"
    forced = as_json(cli("workspace", "unlock", "--force", "--yes", "--json"))
    assert forced["result"]["lock"] == {"locked": False, "reasons": []} and forced["result"]["forced"]
    assert any("警告" in n for n in forced["notices"])
    assert as_json(cli("workspace", "list", "--json"))["result"]["modules"][0]["lock"]["locked"] is False


def test_running_commands_lock_the_workspace(cli, module, monkeypatch):
    seen = []

    def check(self, **options):
        seen.append([(r.kind, r.pid) for r in locks.status(self.root).reasons])
        return CheckReport((CheckItem("generated", True, ""),))

    monkeypatch.setattr(type(module), "check", check)
    assert cli("check", "--json").exit_code == 0
    assert seen == [[("command", os.getpid())]] and not locks.status(module.root).locked


def test_other_workspace_lock_stops_deleting_its_task_branch(cli, module, parallel, monkeypatch):
    monkeypatch.chdir(parallel)
    cli("workspace", "lock", "--reason", "作業中")
    monkeypatch.chdir(module.root)
    listed = as_json(cli("workspace", "list", "--json"))["result"]["modules"][0]["workspaces"]
    assert [w["lock"]["locked"] for w in listed] == [True]
    for args in (("task", "drop", "1", "--yes"), ("task", "close", "1", "--yes")):
        refused = as_json(cli(*args, "--json"))["error"]
        assert refused["code"] == "workspace_locked", args
        assert str(parallel) in refused["details"][0] or parallel.as_posix() in refused["details"][0]
    assert as_json(cli("task", "status", "1", "--json"))["result"]["remote"]       # GitHubのタスクブランチも残っている
    assert git(parallel, "status", "--porcelain").strip() == ""                    # lock.json はコミット対象にならない
    monkeypatch.chdir(parallel)
    cli("workspace", "unlock")
    monkeypatch.chdir(module.root)
    assert cli("task", "drop", "1", "--yes", "--json").exit_code == 0


def test_new_workspace_for_another_task_is_not_refused(cli, module, parallel, monkeypatch):
    monkeypatch.chdir(parallel)
    cli("workspace", "lock")
    cli("task", "new", "もう1つ")
    assert cli("task", "start", "2", "--name", "b", "--json").exit_code == 0
