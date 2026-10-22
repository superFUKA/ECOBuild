"""task status・task list の表示：本文・子タスクの様子・提出（list と同じ作り方）・作業役が作業中のタスク。"""

import json

import pytest
from click.testing import CliRunner

from helpers import git, write
from ecowork import github as _github
from ecobuild_cli import build_cli

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
    return json.loads(result.stdout)["result"]


def test_status_shows_the_body_and_the_rest_with_body_option(cli):
    body = "\n".join(f"{i} 行目" for i in range(1, 16))
    number = as_json(cli("task", "new", "本文のあるタスク", "--body", body, "--json"))["task"]["number"]
    shown = cli("task", "status", str(number)).output
    assert "本文：" in shown and "10 行目" in shown and "11 行目" not in shown and "ほか 5 行" in shown
    assert "15 行目" in cli("task", "status", str(number), "--body").output


def test_status_submission_matches_list(cli, module, monkeypatch):
    number = as_json(cli("task", "new", "提出するタスク", "--json"))["task"]["number"]
    work = as_json(cli("task", "start", str(number), "--name", "提出", "--json"))["workspace"]
    monkeypatch.chdir(work)   # 作業は作業空間（.ecobuild/w/<番号>）で
    write(module.root / ".ecobuild" / "w" / str(number) / "a.txt", "a\n")
    git(work, "add", "a.txt")
    cli("task", "commit", "--message", "a")
    assert cli("task", "submit", "--no-check", "--partial").exit_code == 0
    status = as_json(cli("task", "status", "--json"))
    listed = next(t for t in as_json(cli("task", "list", "--json")) if t["number"] == number)
    assert status["pull_request"]["state"] == "open"
    assert status["task"]["submission"] == listed["submission"] and listed["submission"]["partial"]
    assert "中間提出中" in cli("task", "status").output


def test_parent_status_lists_children_with_their_state(cli, module):
    parent = as_json(cli("task", "new", "親", "--json"))["task"]["number"]
    started = as_json(cli("task", "new", "作業中の子", "--parent", str(parent), "--json"))["task"]["number"]
    waiting = as_json(cli("task", "new", "未着手の子", "--parent", str(parent), "--json"))["task"]["number"]
    git(module.root, "switch", "--quiet", "main")
    cli("task", "start", str(started), "--name", "子")
    git(module.root, "switch", "--quiet", "main")
    status = as_json(cli("task", "status", str(parent), "--json"))
    children = {c["number"]: c for c in status["children"]}
    assert set(children) == {started, waiting}
    assert children[started]["task_branch"] and not children[waiting]["task_branch"]
    shown = cli("task", "status", str(parent)).output
    assert f"#{started} 作業中の子" in shown and "タスクブランチあり" in shown.split(f"#{started}")[1].splitlines()[0]
    assert "タスクブランチあり" not in shown.split(f"#{waiting} ")[1].splitlines()[0]


def test_task_of_a_working_child_shows_the_agent_instead_of_start(cli, module):
    """エージェントが起動した子（子タスクの持ち主。記録 agents）が作業中のタスクは、task start で再開とは案内しない。"""
    from ecobuild_agent import agents
    number = as_json(cli("task", "new", "子のタスク", "--json"))["task"]["number"]
    parent = agents.create(registration="manager", workspace=module.root)
    place = module.root / ".ecobuild" / "w" / str(number)
    place.mkdir(parents=True)
    child = agents.create(registration="worker", workspace=place, parent=parent.id, name="係",
                          task={"number": number, "branch": f"task/{number}-係"})
    shown = cli("task", "status", str(number)).output
    assert f"エージェント 係（{child.id}・登録 worker）が作業中" in shown and "task start" not in shown
    status = as_json(cli("task", "status", str(number), "--json"))
    assert status["worker"]["name"] == "係" and status["workspace"]
    listed = next(t for t in as_json(cli("task", "list", "--json")) if t["number"] == number)
    assert listed["worker"]["name"] == "係" and listed["worker"]["id"] == child.id
    assert "エージェント 係" in cli("task", "list").output
