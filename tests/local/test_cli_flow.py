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
    for args in (["new"], ["build"], ["test"], ["run"], ["status"], ["task", "add"], ["task", "commit"], ["task", "push"], ["restore"],
                 ["sync"], ["sync", "continue"], ["sync", "abort"], ["stash"], ["stash", "pop"], ["stash", "list"],
                 ["branch", "create"], ["branch", "list"], ["branch", "delete"], ["branch", "submit"],
                 ["branch", "merge"], ["task", "new"], ["task", "start"], ["task", "submit"], ["task", "merge"],
                 ["task", "clean"], ["task", "drop"], ["pr", "list"], ["pr", "status"], ["pr", "diff"],
                 ["pr", "comment"], ["pr", "review"], ["pr", "edit"], ["pr", "close"], ["pr", "reopen"], ["pr", "ready"],
                 ["pr", "draft"], ["milestone", "list"], ["milestone", "create"], ["milestone", "edit"],
                 ["milestone", "close"], ["milestone", "reopen"], ["board", "list"], ["board", "use"], ["board", "show"],
                 ["board", "unset"], ["board", "sync"], ["task", "field", "set"], ["task", "field", "clear"]):
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
    assert cli("task", "add", "calc.cpp", "--json").exit_code == 0
    assert as_json(cli("task", "commit", "--message", "計算を追加", "--json"))["result"]["branch"] == "task/1"
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
    assert cli("task", "add", "a.txt").exit_code == 0
    assert cli("task", "commit", "--message", "途中").exit_code == 0
    refused = cli("task", "drop", "--json")
    assert refused.exit_code == 1 and as_json(refused)["error"]["code"] == "confirmation_required"
    dropped = as_json(cli("task", "drop", "--close", "--yes", "--json"))["result"]
    assert dropped["lost_commits"] == ["途中"] and dropped["switched_to"] == "main" and dropped["issue_closed"]
    human = cli("task", "drop")
    assert human.exit_code == 1  # もう作業空間にいない


def test_errors_are_reported_as_json(cli, module):
    result = cli("task", "commit", "--message", "x", "--json")
    assert result.exit_code == 1
    document = as_json(result)
    assert document["ok"] is False and document["error"]["code"] == "not_in_workspace"
    assert document["error"]["hint"] and document["module"] == module.root.resolve().as_posix()
    assert result.stdout.count("\n") == 1  # 標準出力にはJSONが1つだけ


def test_human_output_and_usage_error(cli):
    result = cli("task", "commit")
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


def test_optional_arguments_are_also_positional(cli, module):
    """省略可能な引数は、位置引数でもオプションでも指定できる（task status 1 と task status --issue 1）。"""
    as_json(cli("task", "new", "位置引数", "--start", "--json"))
    by_position = as_json(cli("task", "status", "1", "--json"))["result"]
    assert by_position["number"] == 1
    assert as_json(cli("task", "status", "--issue", "1", "--json"))["result"]["number"] == 1
    for args in (["task", "status", "1", "2"], ["task", "status", "1", "--issue", "1"]):
        result = cli(*args, "--json")
        assert result.exit_code == 2 and as_json(result)["error"]["code"] == "usage_error", args
    assert cli("task", "status", "1", "2").exit_code == 2  # 人向けでも用法エラー
    assert cli("show", "HEAD", "--json").exit_code == 0
    assert as_json(cli("task", "revert", "--json"))["error"]["code"] == "usage_error"


def test_task_remove_and_resume(cli, module):
    as_json(cli("task", "new", "手元を消す", "--start", "--json"))
    write(module.root / "a.txt", "a\n")
    assert cli("task", "add", "a.txt").exit_code == 0
    assert cli("task", "commit", "--message", "途中").exit_code == 0
    refused = as_json(cli("task", "remove", "--json"))
    assert refused["error"]["code"] == "commits_would_be_lost"
    assert cli("task", "push").exit_code == 0
    removed = cli("task", "remove")
    assert removed.exit_code == 0 and "ecobuild task start 1" in removed.stdout
    assert "- #1" in cli("task", "list").stdout  # GitHubにだけある
    resumed = as_json(cli("task", "start", "1", "--json"))["result"]
    assert resumed["branch"] == "task/1" and (module.root / "a.txt").exists()


def test_task_clean_without_targets(cli):
    result = cli("task", "clean")
    assert result.exit_code == 0 and "片付ける作業空間はありません" in result.stdout


def test_task_labels_assignees_and_comments(cli, module):
    as_json(cli("task", "new", "落ちる", "--label", "bug,urgent", "--start", "--json"))
    as_json(cli("task", "new", "説明", "--label", "docs", "--json"))
    listed = cli("task", "list", "--label", "bug")
    assert "#1 落ちる [bug] [urgent]（担当：tester）" in listed.stdout and "#2" not in listed.stdout
    assert [t["number"] for t in as_json(cli("task", "list", "--assignee", "@me", "--json"))["result"]] == [1]
    assert cli("task", "comment", "--message", "計算は済み").exit_code == 0
    assert cli("task", "edit", "2", "--add-assignee", "@me", "--remove-label", "docs").exit_code == 0
    status = cli("task", "status")
    assert "ラベル：bug, urgent" in status.stdout and "tester：計算は済み" in status.stdout
    assert as_json(cli("task", "comment", "--json"))["error"]["code"] == "usage_error"
    assert as_json(cli("ci", "init", "--shared", "yes", "--json"))["error"]["code"] == "usage_error"


def test_draft_pull_request_can_be_made_ready(cli, module):
    """下書きのPRはマージできず、案内される ecobuild pr ready で解除してからマージできる。"""
    assert cli("task", "new", "下書き", "--start").exit_code == 0
    write(module.root / "a.txt", "a\n")
    cli("task", "add", "a.txt")
    cli("task", "commit", "--message", "a")
    pr = as_json(cli("task", "submit", "--draft", "--json"))["result"]
    assert pr["draft"]
    refused = as_json(cli("task", "merge", "--json"))
    assert refused["error"]["code"] == "pull_request_draft" and "ecobuild pr ready" in refused["error"]["hint"]
    assert as_json(cli("pr", "list", "--json"))["result"][0]["number"] == pr["number"]
    assert not as_json(cli("pr", "ready", str(pr["number"]), "--json"))["result"]["draft"]
    status = as_json(cli("pr", "status", "--json"))["result"]
    assert (status["number"], status["task"], status["draft"]) == (pr["number"], 1, False)
    assert cli("pr", "edit", "--clear-body", "--json").exit_code == 0
    assert as_json(cli("task", "merge", "--json"))["result"]["closed_issue"] == 1


def test_task_relations_from_cli(cli):
    assert cli("milestone", "create", "v1", "--due", "2026-10-31").exit_code == 0
    assert cli("task", "new", "親").exit_code == 0
    assert cli("task", "new", "先", "--parent", "1").exit_code == 0
    assert cli("task", "new", "後", "--parent", "1", "--blocked-by", "#2", "--milestone", "v1").exit_code == 0
    assert cli("task", "new", "誤り", "--blocked-by", "x").exit_code == 2
    ready = as_json(cli("task", "list", "--ready", "--json"))["result"]
    assert [t["number"] for t in ready] == [2]
    blocked = as_json(cli("task", "start", "3", "--json"))
    assert blocked["error"]["code"] == "task_blocked" and "--ignore-blocked" in blocked["error"]["hint"]
    status = as_json(cli("task", "status", "1", "--json"))["result"]
    assert [s["number"] for s in status["subtasks"]] == [2, 3]
    assert "v1" in cli("milestone", "list").output


def test_board_from_cli(cli, module):
    github = module.repository.github
    board = github.add_board(statuses=("Todo", "In Progress", "Done"))
    assert as_json(cli("board", "use", board.url, "--json"))["error"]["code"] == "not_in_workspace"
    assert cli("task", "new", "ボードをつなぐ", "--start").exit_code == 0
    used = as_json(cli("board", "use", board.url, "--json"))["result"]
    assert used["stages"] == {"todo": "Todo", "in_progress": "In Progress", "done": "Done"}
    assert "[board]" in (module.root / "ecobuild.toml").read_text(encoding="utf-8")
    assert board.id in github.linked_boards
    assert "In Progress" in cli("board", "show").output
    synced = as_json(cli("board", "sync", "--json"))["result"]
    assert synced["added"] == [1] and synced["changed"][0]["after"] == "In Progress"
    assert cli("task", "new", "調べる").exit_code == 0
    assert as_json(cli("task", "list", "--json"))["result"][1]["status"] == "Todo"
    assert cli("task", "start", "2", "--no-workspace").exit_code == 0
    refused = as_json(cli("task", "field", "set", "2", "--field", "Status", "--value", "Done", "--json"))
    assert refused["error"]["code"] == "stage_field"
    assert as_json(cli("task", "status", "2", "--json"))["result"]["board"] == {"Status": "In Progress"}
    assert cli("board", "unset").exit_code == 0 and board.id not in github.linked_boards
