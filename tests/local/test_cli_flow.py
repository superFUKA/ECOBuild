import json

import pytest
from click.testing import CliRunner

from helpers import git, write
from ecowork import github as _github
from ecobuild.cli import build_cli

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


def test_every_command_has_help():
    runner = CliRunner()
    for args in (["new"], ["build"], ["test"], ["run"], ["status"], ["add"], ["commit"], ["push"], ["restore"],
                 ["sync"], ["sync", "continue"], ["sync", "abort"], ["stash"], ["stash", "pop"], ["stash", "list"],
                 ["branch", "create"], ["branch", "list"], ["branch", "delete"], ["branch", "submit"],
                 ["branch", "merge"], ["task", "new"], ["task", "start"], ["task", "submit"], ["task", "merge"],
                 ["task", "clean"], ["task", "drop"]):
        result = runner.invoke(build_cli(), [*args, "--help"])
        assert result.exit_code == 0, (args, result.output)
        assert "--json" in result.output, args


def test_cli_full_cycle(cli, module):
    result = cli("task", "new", "0除算対策", "--start", "--json")
    assert result.exit_code == 0
    document = as_json(result)
    assert document["ok"] and document["result"]["workspace"]["branch"] == "task/1"
    assert "_module" not in document["result"]["task"]

    write(module.root / "calc.cpp", "int calc;\n")
    assert cli("add", "calc.cpp", "--json").exit_code == 0
    assert as_json(cli("commit", "--message", "計算を追加", "--json"))["result"]["branch"] == "task/1"
    status = as_json(cli("status", "--json"))["result"]
    assert status["workspace"] == 1 and status["staged"] == []

    pr = as_json(cli("task", "submit", "--json"))["result"]
    assert pr["head"] == "task/1" and pr["base"] == "main"
    merged = as_json(cli("task", "merge", "--json"))["result"]
    assert merged["closed_issue"] == 1

    # 確認が必要な操作は、--json時に--yesがなければ失敗する
    refused = cli("task", "clean", "--json")
    assert refused.exit_code == 1 and as_json(refused)["error"]["code"] == "confirmation_required"
    cleaned = as_json(cli("task", "clean", "--yes", "--json"))["result"]
    assert cleaned["removed"] == ["task/1"] and cleaned["switched_to"] == "main"
    assert git(module.root, "branch", "--show-current") == "main"


def test_task_drop_confirms_lost_commits(cli, module):
    as_json(cli("task", "new", "やめる作業", "--start", "--json"))
    write(module.root / "a.txt", "a\n")
    assert cli("add", "a.txt").exit_code == 0
    assert cli("commit", "--message", "途中").exit_code == 0
    refused = cli("task", "drop", "--json")
    assert refused.exit_code == 1 and as_json(refused)["error"]["code"] == "confirmation_required"
    dropped = as_json(cli("task", "drop", "--close", "--yes", "--json"))["result"]
    assert dropped["lost_commits"] == ["途中"] and dropped["switched_to"] == "main" and dropped["issue_closed"]
    human = cli("task", "drop")
    assert human.exit_code == 1  # もう作業空間にいない


def test_errors_are_reported_as_json(cli, module):
    result = cli("commit", "--message", "x", "--json")
    assert result.exit_code == 1
    document = as_json(result)
    assert document["ok"] is False and document["error"]["code"] == "not_in_workspace"
    assert document["error"]["hint"] and document["module"] == module.root.resolve().as_posix()
    assert result.stdout.count("\n") == 1  # 標準出力にはJSONが1つだけ


def test_human_output_and_usage_error(cli):
    result = cli("commit")
    assert result.exit_code == 2  # --message がない
    result = cli("branch", "create", "develop")
    assert result.exit_code == 0 and "develop" in result.stdout
    listed = cli("branch", "list")
    assert "develop" in listed.stdout and "main" in listed.stdout


def test_sync_continue_and_abort_commands(cli):
    result = cli("sync", "continue", "--json")
    assert as_json(result)["error"]["code"] == "no_sync_in_progress"
    assert as_json(cli("sync", "--json"))["result"]["branch"] == "main"


def test_not_in_module(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(build_cli(), ["status", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "not_in_module"
