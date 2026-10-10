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
                 ["milestone", "close"], ["milestone", "reopen"], ["task", "next"], ["task", "overdue"],
                 ["task", "plan"], ["task", "workload"], ["sprint", "list"], ["sprint", "status"], ["milestone", "status"], ["init"]):
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
    assert "#1 落ちる〈作業中〉 [bug] [urgent]（担当：tester）" in listed.stdout and "#2" not in listed.stdout
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


def test_task_stages_from_cli(cli, module):
    """利用者はタスクだけを扱う：段階は ECOBuild の言葉で表示し、置き場所（ボード）のコマンド・値は出さない。"""
    assert cli("board", "show").exit_code == 2 and cli("task", "field", "set").exit_code == 2
    assert cli("task", "new", "調べる").exit_code == 0
    assert "#1 調べる〈未着手〉" in cli("task", "list").stdout
    listed = as_json(cli("task", "list", "--json"))["result"][0]
    assert listed["stage"] == "todo" and "status" not in listed and "fields" not in listed
    assert cli("task", "start", "1", "--no-workspace").exit_code == 0
    status = as_json(cli("task", "status", "1", "--json"))["result"]
    assert status["task"]["stage"] == "in_progress" and "board" not in status
    assert "段階：作業中" in cli("task", "status", "1").stdout
    assert "ボード" not in cli("task", "--help").output and "ボード" not in cli("--help").output


def test_planning_from_cli(cli, module):
    import datetime
    for title in ("低", "高", "遅れ"):
        assert cli("task", "new", title).exit_code == 0
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    planned = as_json(cli("task", "plan", "1", "--priority", "Low", "--sprint", "current", "--estimate", "1",
                          "--json"))["result"]
    assert (planned["priority"], planned["sprint"], planned["estimate"]) == ("Low", "Sprint 1", 1.0)
    assert cli("task", "plan", "2", "--priority", "High", "--estimate", "3").exit_code == 0
    assert cli("task", "plan", "3", "--due", yesterday).exit_code == 0
    ranked = as_json(cli("task", "next", "--json"))["result"]
    assert [n["task"]["number"] for n in ranked] == [3, 1, 2] and ranked[0]["reasons"][0].startswith("期限切れ")
    assert "理由" in cli("task", "next").output
    assert [t["number"] for t in as_json(cli("task", "overdue", "--json"))["result"]["overdue"]] == [3]
    sprint = as_json(cli("sprint", "status", "--json"))["result"]
    assert (sprint["sprint"]["name"], sprint["total"]) == ("Sprint 1", 1)
    assert "Sprint 1" in cli("sprint", "list").output
    assert [t["number"] for t in as_json(cli("task", "list", "--sprint", "current", "--json"))["result"]] == [1]
    load = as_json(cli("task", "workload", "--json"))["result"]
    assert sum(w["open"] for w in load) == 3
    assert as_json(cli("task", "list", "--sort", "priority", "--json"))["result"][0]["number"] == 2
    assert as_json(cli("task", "list", "--sort", "Priority", "--json"))["error"]["code"] == "invalid_argument"
    assert as_json(cli("task", "status", "3", "--json"))["result"]["task"]["due"] == yesterday
    assert as_json(cli("task", "plan", "1", "--priority", "最高", "--json"))["error"]["code"] == "invalid_argument"


def test_task_dates_from_cli(cli, module):
    """追加した日・開始日・終了日は自動で記録し、期限・開始予定日・終了予定日は作成時と更新で設定する。"""
    import datetime
    today = datetime.date.today().isoformat()
    made = cli("task", "new", "日付", "--due", "2026-11-30", "--planned-start", "2026-11-02",
               "--planned-end", "2026-11-20")
    assert made.exit_code == 0
    task = as_json(cli("task", "status", "1", "--json"))["result"]["task"]
    assert (task["due"], task["planned_start"], task["planned_end"]) == ("2026-11-30", "2026-11-02", "2026-11-20")
    assert (task["created"], task["started"], task["finished"]) == (today, None, None)
    assert as_json(cli("task", "new", "逆", "--planned-start", "2026-11-20", "--planned-end", "2026-11-02",
                       "--json"))["error"]["code"] == "invalid_argument"
    assert cli("task", "edit", "1", "--planned-end", "2026-11-25", "--clear-date", "due").exit_code == 0
    assert as_json(cli("task", "edit", "1", "--clear-date", "priority", "--json"))["error"]["code"] == "invalid_argument"
    assert cli("task", "plan", "1", "--planned-start", "2026-11-03").exit_code == 0
    assert cli("task", "start", "1", "--no-workspace").exit_code == 0
    task = as_json(cli("task", "status", "1", "--json"))["result"]["task"]
    assert (task["due"], task["planned_start"], task["planned_end"], task["started"]) == (
        None, "2026-11-03", "2026-11-25", today)
    assert cli("task", "close", "1").exit_code == 0
    shown = cli("task", "status", "1").output
    assert f"日付：追加 {today}・開始 {today}・終了 {today}" in shown and "予定 2026-11-03〜2026-11-25" in shown


def test_legacy_board_setting_is_taken_over(cli, module):
    """以前の設定（ecobuild.toml の [board]）でつないでいたボードは、そのまま引き継ぐ（設定を変える必要はない）。"""
    github = module.repository.github
    for board in list(github.boards.values()):        # モジュールを作ったときのものは外す（以前の状態にする）
        github.link_board(module.root, board.id, link=False)
    old = github.add_board(statuses=("Todo", "In Progress", "Done"))
    github.link_board(module.root, old.id, link=True)
    config = module.root / "ecobuild.toml"
    config.write_text(config.read_text(encoding="utf-8") + f'\n[board]\nurl = "{old.url}"\n', encoding="utf-8")
    assert cli("task", "new", "引き継ぐ").exit_code == 0
    assert github.ecobuild_board().id == old.id
    assert as_json(cli("task", "list", "--json"))["result"][0]["stage"] == "todo"


def test_subtasks_from_cli(cli, module):
    """子タスクの作業空間は親の作業空間から派生し、子が終わるまで親は終了できない（コマンドで一周）。"""
    def work(name):
        write(module.root / name, name + "\n")
        assert cli("task", "add", name).exit_code == 0
        assert cli("task", "commit", "--message", name).exit_code == 0

    assert cli("task", "new", "親").exit_code == 0
    assert cli("task", "new", "子", "--parent", "1").exit_code == 0
    assert as_json(cli("task", "start", "2", "--base", "main", "--json"))["error"]["code"] == "invalid_base"
    started = cli("task", "start", "2")
    assert started.exit_code == 0 and "作成元 task/1" in started.output and "task/1 をGitHubに作りました" in started.output
    work("child.txt")
    pr = as_json(cli("task", "submit", "--json"))["result"]
    assert pr["base"] == "task/1"
    assert as_json(cli("task", "merge", "--json"))["result"]["closed_issue"] == 2

    assert cli("task", "new", "子2", "--parent", "1").exit_code == 0
    assert cli("task", "start", "1").exit_code == 0
    assert (module.root / "child.txt").exists()
    work("parent.txt")
    submitted = cli("task", "submit")
    assert submitted.exit_code == 0 and "子タスクが終わるまでマージできません" in submitted.output
    refused = as_json(cli("task", "merge", "--json"))
    assert refused["error"]["code"] == "open_subtasks" and "#4" in " ".join(refused["error"]["details"])   # PRとIssueは番号を共有（#3 は子のPR）
    assert as_json(cli("task", "close", "1", "--json"))["error"]["code"] == "open_subtasks"
    assert as_json(cli("task", "drop", "1", "--close", "--yes", "--json"))["error"]["code"] == "open_subtasks"

    closed = cli("task", "close", "4")                       # 作業空間なしで閉じた子
    assert closed.exit_code == 0 and "子タスクはすべて閉じました" in closed.output
    assert cli("task", "start", "1").exit_code == 0
    assert as_json(cli("task", "merge", "--json"))["result"]["closed_issue"] == 1
    assert cli("task", "clean", "--yes").exit_code == 0
    assert cli("sync").exit_code == 0
    assert (module.root / "child.txt").exists() and (module.root / "parent.txt").exists()
