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
    return json.loads(result.stdout)


def test_every_command_has_help():
    runner = CliRunner()
    for args in (["module", "new"], ["module", "clone"], ["module", "types"], ["module", "list"], ["module", "show"],
                 ["workspace", "list"], ["workspace", "create"], ["workspace", "add"], ["workspace", "forget"], ["workspace", "close"],
                 ["container", "status"], ["container", "on"], ["container", "off"], ["container", "start"],
                 ["container", "stop"], ["container", "remove"],
                 ["module", "archive"], ["module", "unarchive"], ["module", "delete"], ["deps", "tree"], ["deps", "add"],
                 ["deps", "remove"],
                 ["build"], ["test"], ["run"], ["status"], ["task", "add"], ["task", "commit"], ["task", "push"], ["restore"],
                 ["sync"], ["sync", "continue"], ["sync", "abort"], ["stash"], ["stash", "pop"], ["stash", "list"],
                 ["branch", "create"], ["branch", "list"], ["branch", "delete"], ["branch", "submit"],
                 ["branch", "merge"], ["task", "new"], ["task", "start"], ["task", "submit"], ["task", "finish"],
                 ["task", "approve"], ["task", "reject"], ["task", "withdraw"], ["task", "review"], ["task", "diff"],
                 ["task", "revert"], ["task", "reset"], ["task", "prune"], ["task", "drop"], ["track"], ["track", "add"],
                 ["track", "remove"], ["milestone", "list"], ["milestone", "create"], ["milestone", "edit"],
                 ["milestone", "close"], ["milestone", "reopen"], ["task", "next"], ["task", "overdue"],
                 ["task", "edit"], ["task", "workload"], ["sprint", "list"], ["sprint", "status"], ["milestone", "status"],
                 ["agent", "start"], ["init"]):
        result = runner.invoke(build_cli("cpp"), [*args, "--help"])
        assert result.exit_code == 0, (args, result.output)
        assert "--json" in result.output, args


def test_old_commands_are_gone():
    """pr グループ・task merge／remove／plan はなくした（task finish・task prune <番号>・task edit 等）。"""
    runner = CliRunner()
    for args in (["pr", "list"], ["task", "merge"], ["task", "remove"], ["task", "plan"], ["task", "clean"], ["link"],
                 ["unlink"]):
        assert runner.invoke(build_cli(), [*args, "--help"]).exit_code == 2, args
    shown = runner.invoke(build_cli(), ["task", "--help"]).output
    assert shown.index("計画:") < shown.index("作業:") < shown.index("提出と完了:")


def test_cli_full_cycle(cli, module):
    result = cli("task", "new", "0除算対策", "--start", "--json")
    assert result.exit_code == 0
    document = as_json(result)
    assert document["ok"] and document["result"]["task_branch"]["branch"] == "task/1"
    assert "_module" not in document["result"]["task"]

    write(module.root / "calc.cpp", "int calc;\n")
    write(module.root / "notes.tmp", "メモ\n")          # 管理するファイルの対象外
    status = as_json(cli("status", "--json"))["result"]
    assert status["excluded"] == ["notes.tmp"]
    committed = as_json(cli("task", "commit", "--message", "計算を追加", "--json"))["result"]
    assert committed["branch"] == "task/1" and committed["files"] == ["calc.cpp"]
    assert committed["skipped"] == ["notes.tmp"]
    status = as_json(cli("status", "--json"))["result"]
    assert status["task"] == 1 and status["staged"] == [] and status["untracked"] == ["notes.tmp"]

    pr = as_json(cli("task", "submit", "--no-check", "--json"))["result"]
    assert pr["head"] == "task/1" and pr["base"] == "main"
    finished = cli("task", "finish")
    assert finished.exit_code == 0 and "完了しました：#1 0除算対策" in finished.stdout
    assert git(module.root, "branch", "--show-current") == "main"
    assert "task/1" not in git(module.root, "branch", "--list")
    assert cli("task", "prune").stdout.strip() == "片付けるタスクブランチはありません"


def test_commit_paths_and_track(cli, module):
    """パスを書けば対象外のファイルも含める。管理するファイルは ecobuild track で足せる。"""
    assert cli("task", "new", "記録", "--start").exit_code == 0
    write(module.root / "data" / "a.json", "{}\n")
    write(module.root / "b.json", "{}\n")
    nothing = as_json(cli("task", "commit", "--message", "x", "--json"))
    assert nothing["error"]["code"] == "nothing_to_commit" and "data/a.json" in nothing["error"]["hint"]
    chosen = as_json(cli("task", "commit", "data", "--message", "データ", "--json"))["result"]
    assert chosen["files"] == ["data/a.json"] and chosen["outside"] == ["data/a.json"]
    listed = as_json(cli("track", "--json"))["result"]
    assert {"pattern": "*.cpp", "source": "type", "excluded": False} in listed["patterns"]
    assert cli("track", "add", "*.json").exit_code == 0
    assert 'include = ["*.json"]' in (module.root / ".ecobuild" / "ecobuild.toml").read_text(encoding="utf-8")
    committed = as_json(cli("task", "commit", "--message", "設定とデータ", "--json"))["result"]
    assert set(committed["files"]) == {"b.json"}   # ecobuild.toml は track add がそのままコミットした（ECOBuild 自身のファイル）
    assert cli("track", "remove", "*.md").exit_code == 0
    assert 'exclude = ["*.md"]' in (module.root / ".ecobuild" / "ecobuild.toml").read_text(encoding="utf-8")
    assert as_json(cli("track", "remove", ".ecobuild/ecobuild.toml", "--json"))["error"]["code"] == "invalid_argument"
    write(module.root / "doc.md", "x\n")
    assert as_json(cli("status", "--json"))["result"]["excluded"] == ["doc.md"]


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
    assert human.exit_code == 1  # もうタスクブランチにいない


def test_errors_are_reported_as_json(cli, module):
    result = cli("task", "commit", "--message", "x", "--json")
    assert result.exit_code == 1
    document = as_json(result)
    assert document["ok"] is False and document["error"]["code"] == "not_on_task_branch"
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


def test_task_clean_one_and_resume(cli, module):
    """task prune <番号>：開いているタスクなら、手元の写しだけを消す（以前の task remove）。"""
    as_json(cli("task", "new", "手元を消す", "--start", "--json"))
    write(module.root / "a.txt", "a\n")
    assert cli("task", "commit", "a.txt", "--message", "途中").exit_code == 0
    refused = as_json(cli("task", "prune", "1", "--json"))
    assert refused["error"]["code"] == "commits_would_be_lost"
    assert cli("task", "push").exit_code == 0
    removed = cli("task", "prune", "1")
    assert removed.exit_code == 0 and "ecobuild task start 1" in removed.stdout
    assert "- #1" in cli("task", "list").stdout  # GitHubにだけある
    resumed = as_json(cli("task", "start", "1", "--json"))["result"]
    assert resumed["branch"] == "task/1" and (module.root / "a.txt").exists()


def test_task_clean_without_targets(cli):
    result = cli("task", "prune")
    assert result.exit_code == 0 and "片付けるタスクブランチはありません" in result.stdout


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


def test_draft_submission_can_be_made_ready(cli, module):
    """下書きの提出は完了できず、案内される ecobuild task submit で解除してから完了できる。"""
    assert cli("task", "new", "下書き", "--start").exit_code == 0
    write(module.root / "a.cpp", "a\n")
    cli("task", "commit", "--message", "a")
    pr = as_json(cli("task", "submit", "--draft", "--no-check", "--json"))["result"]
    assert pr["draft"]
    refused = as_json(cli("task", "finish", "--json"))
    assert refused["error"]["code"] == "pull_request_draft" and "ecobuild task submit" in refused["error"]["hint"]
    listed = as_json(cli("task", "list", "--submitted", "--json"))["result"]
    assert [t["number"] for t in listed] == [1] and listed[0]["submission"]["draft"]
    assert "（下書きの提出中）" in cli("task", "list").stdout
    assert not as_json(cli("task", "submit", "--no-check", "--json"))["result"]["draft"]
    status = as_json(cli("task", "status", "--json"))["result"]
    assert (status["pull_request"]["number"], status["pull_request"]["draft"]) == (pr["number"], False)
    assert "+a" in as_json(cli("task", "diff", "1", "--json"))["result"]
    assert as_json(cli("task", "withdraw", "--json"))["result"]["state"] == "closed"
    assert as_json(cli("task", "list", "--submitted", "--json"))["result"] == []
    assert as_json(cli("task", "finish", "--json"))["result"]["closed_issue"] == 1   # 取り下げた後も、完了で出し直す


def test_submit_refuses_uncommitted_changes(cli, module):
    assert cli("task", "new", "未記録", "--start").exit_code == 0
    write(module.root / "a.cpp", "a\n")
    refused = as_json(cli("task", "submit", "--no-check", "--json"))
    assert refused["error"]["code"] == "dirty_working_tree" and refused["error"]["details"] == ["a.cpp"]
    write(module.root / "ignored.tmp", "x\n")       # 管理しないファイルは止めない
    cli("task", "commit", "--message", "a")
    assert cli("task", "submit", "--no-check").exit_code == 0


def test_review_approve_and_reject_from_cli(cli, module):
    """番号はタスクの番号。自分の提出は承認できず、task finish を案内する。"""
    from dataclasses import replace
    assert cli("task", "new", "見てもらう", "--start").exit_code == 0
    write(module.root / "a.cpp", "a\n")
    cli("task", "commit", "--message", "a")
    cli("task", "submit", "--no-check")
    own = as_json(cli("task", "approve", "1", "--json"))
    assert own["error"]["code"] == "own_pull_request" and "task finish 1" in own["error"]["hint"]
    github = module.repository.github
    number = module.repository.submission(1).number
    github.pulls[number] = replace(github.pulls[number], author="someone")
    assert cli("task", "reject", "1").exit_code == 2         # 理由がない
    assert "#1 を差し戻しました" in cli("task", "reject", "1", "--message", "直して").stdout
    reviewed = cli("task", "review", "1")
    assert reviewed.exit_code == 0 and "task approve 1" in reviewed.stdout
    assert "#1 の提出を確認中" in cli("status").stdout
    approved = cli("task", "approve", "1", "--message", "よい")
    assert approved.exit_code == 0 and "承認して完了しました：#1" in approved.stdout
    assert "確認の前の場所 task/1 に戻りました" in approved.stdout
    assert git(module.root, "branch", "--show-current") == "main" and "task/1" not in git(module.root, "branch")


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
    assert cli("task", "start", "1", "--no-branch").exit_code == 0
    status = as_json(cli("task", "status", "1", "--json"))["result"]
    assert status["task"]["stage"] == "in_progress" and "board" not in status
    assert "段階：作業中" in cli("task", "status", "1").stdout
    assert "ボード" not in cli("task", "--help").output and "ボード" not in cli("--help").output


def test_planning_from_cli(cli, module):
    import datetime
    for title in ("低", "高", "遅れ"):
        assert cli("task", "new", title).exit_code == 0
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    planned = as_json(cli("task", "edit", "1", "--priority", "Low", "--sprint", "current", "--estimate", "1",
                          "--json"))["result"]
    assert (planned["priority"], planned["sprint"], planned["estimate"]) == ("Low", "Sprint 1", 1.0)
    assert cli("task", "edit", "2", "--priority", "High", "--estimate", "3").exit_code == 0
    assert cli("task", "edit", "3", "--due", yesterday).exit_code == 0
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
    assert as_json(cli("task", "edit", "1", "--priority", "最高", "--json"))["error"]["code"] == "invalid_argument"
    assert cli("task", "edit", "1", "--clear", "priority,estimate").exit_code == 0
    assert as_json(cli("task", "status", "1", "--json"))["result"]["task"]["priority"] is None


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
    assert cli("task", "edit", "1", "--planned-end", "2026-11-25", "--clear", "due").exit_code == 0
    assert as_json(cli("task", "edit", "1", "--clear", "color", "--json"))["error"]["code"] == "invalid_argument"
    assert as_json(cli("task", "edit", "1", "--json"))["error"]["code"] == "invalid_argument"
    assert cli("task", "edit", "1", "--planned-start", "2026-11-03").exit_code == 0
    assert cli("task", "start", "1", "--no-branch").exit_code == 0
    task = as_json(cli("task", "status", "1", "--json"))["result"]["task"]
    assert (task["due"], task["planned_start"], task["planned_end"], task["started"]) == (
        None, "2026-11-03", "2026-11-25", today)
    assert cli("task", "close", "1").exit_code == 0
    shown = cli("task", "status", "1").output
    assert f"日付：追加 {today}・開始 {today}・終了 {today}" in shown and "予定 2026-11-03〜2026-11-25" in shown


def test_legacy_board_setting_is_taken_over(cli, module):
    """以前の設定（ecobuild.toml の [board]）でつないでいたボードは、そのまま引き継ぐ（設定を変える必要はない）。
    足りない段階（計画中・レビュー待ち）は足し、今ある値は残す。"""
    github = module.repository.github
    for board in list(github.boards.values()):        # モジュールを作ったときのものは外す（以前の状態にする）
        github.link_board(module.root, board.id, link=False)
    old = github.add_board(statuses=("Todo", "In Progress", "Done"))
    github.link_board(module.root, old.id, link=True)
    earlier = github.create_issue(module.root, "以前から", "")
    item = github.add_board_item(module.root, earlier.number, old.id)
    github.set_board_value(module.root, old.id, item.id, old.field("Status"), "In Progress")
    config = module.root / ".ecobuild" / "ecobuild.toml"
    config.write_text(config.read_text(encoding="utf-8") + f'\n[board]\nurl = "{old.url}"\n', encoding="utf-8")
    assert cli("task", "new", "引き継ぐ").exit_code == 0
    assert github.ecobuild_board().id == old.id
    status = github.ecobuild_board().field("Status")
    assert [o.name for o in status.options] == ["Backlog", "Todo", "In Progress", "In Review", "Done"]
    assert {t["title"]: t["stage"] for t in as_json(cli("task", "list", "--json"))["result"]} == \
        {"以前から": "in_progress", "引き継ぐ": "todo"}
    assert cli("task", "edit", "2", "--stage", "planned").exit_code == 0


def test_subtasks_from_cli(cli, module):
    """子タスクのタスクブランチは親のタスクブランチから派生し、子が終わるまで親は終了できない（コマンドで一周）。"""
    def work(name):
        write(module.root / name, name + "\n")
        assert cli("task", "commit", name, "--message", name).exit_code == 0

    assert cli("task", "new", "親").exit_code == 0
    assert cli("task", "new", "子", "--parent", "1").exit_code == 0
    assert as_json(cli("task", "start", "2", "--base", "main", "--json"))["error"]["code"] == "invalid_base"
    started = cli("task", "start", "2")
    assert started.exit_code == 0 and "作成元 task/1" in started.output and "task/1 をGitHubに作りました" in started.output
    work("child.txt")
    pr = as_json(cli("task", "submit", "--no-check", "--json"))["result"]
    assert pr["base"] == "task/1"
    finished = as_json(cli("task", "finish", "--json"))["result"]
    assert finished["closed_issue"] == 2 and finished["switched_to"] == "task/1"

    assert cli("task", "new", "子2", "--parent", "1").exit_code == 0
    assert cli("task", "start", "1").exit_code == 0
    assert (module.root / "child.txt").exists()
    work("parent.txt")
    submitted = cli("task", "submit", "--no-check")
    assert submitted.exit_code == 0 and "子タスクが終わるまで完了できません" in submitted.output
    refused = as_json(cli("task", "finish", "--json"))
    assert refused["error"]["code"] == "open_subtasks" and "#4" in " ".join(refused["error"]["details"])   # PRとIssueは番号を共有（#3 は子のPR）
    assert as_json(cli("task", "close", "1", "--json"))["error"]["code"] == "open_subtasks"
    assert as_json(cli("task", "drop", "1", "--close", "--yes", "--json"))["error"]["code"] == "open_subtasks"

    closed = cli("task", "close", "4")                       # タスクブランチなしで閉じた子
    assert closed.exit_code == 0 and "子タスクはすべて閉じました" in closed.output and "task finish 1" in closed.output
    assert as_json(cli("task", "finish", "1", "--json"))["result"]["closed_issue"] == 1
    assert git(module.root, "branch", "--show-current") == "main"
    assert cli("sync").exit_code == 0
    assert (module.root / "child.txt").exists() and (module.root / "parent.txt").exists()


@pytest.fixture
def may_delete(monkeypatch):
    from ecobuild_bundle import tooling
    monkeypatch.setattr(tooling, "gh_has_scope", lambda scope: True)


def test_module_is_archived_before_deleted(cli, module, may_delete):
    """削除は2段階：archive（元に戻せる）してから delete。delete は名前をもう一度書かないと動かない。"""
    github = module.repository.github
    assert cli("task", "new", "t").exit_code == 0
    assert as_json(cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--json"))["error"]["code"] \
        == "not_archived"
    assert as_json(cli("module", "archive", "tester/remote", "--json"))["error"]["code"] == "confirmation_required"
    archived = cli("module", "archive", "remote", "--owner", "tester", "--yes")
    assert archived.exit_code == 0 and "ecobuild module unarchive tester/remote" in archived.output
    assert github.archived_repositories == ["tester/remote"] and not github.ecobuild_board().closed
    assert cli("module", "unarchive", "tester/remote").exit_code == 0 and github.archived_repositories == []
    assert cli("module", "archive", "tester/remote", "--yes").exit_code == 0

    asked = as_json(cli("module", "delete", "tester/remote", "--json"))
    assert asked["error"]["code"] == "confirmation_required" and "Issue 1 件" in asked["error"]["message"]
    wrong = as_json(cli("module", "delete", "tester/remote", "--confirm", "tester/other", "--json"))
    assert wrong["error"]["code"] == "confirmation_required" and github.deleted_repositories == []
    deleted = cli("module", "delete", "tester/remote", "--confirm", "tester/remote")
    assert deleted.exit_code == 0 and "90日以内なら元に戻せます" in deleted.output
    assert f"作業空間 {module.root} は残しています" in deleted.output
    board = github.ecobuild_board()     # タスク管理の情報は消さずに閉じる
    assert github.deleted_repositories == ["tester/remote"] and board.closed
    assert "（tester/remote）" in github.board_descriptions[board.id]
    assert module.root.exists()


def test_module_list_and_show(cli, module, tmp_path):
    """module list：GitHubにあるモジュール（ecobuild.toml があるもの）。アーカイブしたものは既定で出さない。"""
    github = module.repository.github
    plain = tmp_path / "plain.git"                     # ECOBuildのモジュールでないリポジトリは出さない
    git(tmp_path, "init", "--quiet", "--bare", str(plain))
    github.others["plain"] = plain
    listed = as_json(cli("module", "list", "--json"))["result"]
    assert [(m["repository"], m["type"], m["archived"]) for m in listed] == [("tester/remote", "cpp", False)]
    assert "tester/remote（cpp・非公開" in cli("module", "list").output

    assert cli("module", "archive", "tester/remote", "--yes").exit_code == 0
    assert as_json(cli("module", "list", "--json"))["result"] == []
    assert [m["repository"] for m in as_json(cli("module", "list", "--archived", "--json"))["result"]] \
        == ["tester/remote"]
    assert "アーカイブ済み" in cli("module", "list", "--all").output
    assert as_json(cli("module", "list", "--archived", "--all", "--json"))["error"]["code"] == "usage_error"

    shown = as_json(cli("module", "show", "--json"))["result"]
    assert (shown["name"], shown["repository"], shown["archived"], shown["projects"]) \
        == ("Calc", "tester/remote", True, [])
    assert "リポジトリ：https://example.invalid/tester/remote（非公開・アーカイブ済み）" in cli("module", "show").output


@pytest.fixture
def parallel(cli, module, monkeypatch):
    """タスク #1 を、別の作業空間（モジュールの隣の Calc-1）で始める。型の準備はしない。"""
    from ecobuild.results import PrepareResult
    from ecobuild_cpp.type import CppType
    monkeypatch.setattr(CppType, "prepare", lambda self: PrepareResult((), False))
    assert cli("task", "new", "並行作業").exit_code == 0
    assert cli("task", "start", "1", "--dir", "../Calc-1").exit_code == 0
    monkeypatch.chdir(module.root)
    return module.root.parent / "Calc-1"


def test_workspace_create(cli, module, monkeypatch):
    """作業空間を作る：既定のブランチのclone を記録し、タスクはそこで開始する。"""
    from ecobuild.results import PrepareResult
    from ecobuild_cpp.type import CppType
    monkeypatch.setattr(CppType, "prepare", lambda self: PrepareResult((), False))
    created = as_json(cli("workspace", "create", "../Calc-2", "--json"))["result"]
    other = module.root.parent / "Calc-2"
    assert created["root"] == other.as_posix() and created["name"] == "Calc"
    listed = as_json(cli("workspace", "list", "--json"))["result"]
    assert (other.as_posix(), "main", None) in [(c["path"], c["branch"], c["task"]) for c in listed]
    assert as_json(cli("workspace", "create", "../Calc-2", "--json"))["error"]["code"] == "already_exists"

    assert cli("task", "new", "そこで作業").exit_code == 0
    monkeypatch.chdir(other)
    assert cli("task", "start", "1").exit_code == 0
    assert as_json(cli("status", "--json"))["result"]["branch"] == "task/1"


def test_workspaces(cli, module, parallel, monkeypatch):
    """このPCの作業空間の記録：使ったモジュールと task start --dir の作業空間。タスクブランチのある作業空間も分かる。"""
    listed = as_json(cli("workspace", "list", "--json"))["result"]
    assert sorted((c["path"], c["branch"], c["task"]) for c in listed) == sorted([
        (module.root.as_posix(), "main", None), (parallel.as_posix(), "task/1", 1)])
    assert "task/1＝タスク #1" in cli("workspace", "list").output

    task = as_json(cli("task", "list", "--json"))["result"][0]
    assert task["workspace"] == parallel.as_posix() and not task["task_branch"]
    assert "+ #1 並行作業" in cli("task", "list").output and f"（場所：{parallel}）" in cli("task", "list").output
    status = as_json(cli("task", "status", "1", "--json"))["result"]
    assert status["workspace"] == parallel.as_posix() == status["task"]["workspace"]
    assert "タスクブランチ：task/1" in cli("task", "status", "1").output
    shown = as_json(cli("module", "show", "--json"))["result"]
    assert sorted(c["path"] for c in shown["workspaces"]) == sorted([module.root.as_posix(), parallel.as_posix()])
    assert "このPCの作業空間" in cli("module", "show").output

    assert as_json(cli("workspace", "forget", "../Calc-1", "--json"))["result"]["exists"]
    assert len(as_json(cli("workspace", "list", "--json"))["result"]) == 1
    assert as_json(cli("workspace", "forget", "../Calc-1", "--json"))["error"]["code"] == "workspace_not_recorded"
    assert as_json(cli("workspace", "add", "../Calc-1", "--json"))["result"]["task"] == 1
    nested = module.root / "deps" / "Base"            # 依存先のclone 等、他のモジュールの中のものは記録しない
    write(nested / ".ecobuild" / "ecobuild.toml", "")
    assert as_json(cli("workspace", "add", "deps/Base", "--json"))["error"]["code"] == "invalid_argument"

    git(parallel, "remote", "set-url", "origin", "https://github.com/tester/remote.git")
    module.repository.github.archived_repositories.append("tester/remote")
    fetched = {c["path"]: c for c in as_json(cli("workspace", "list", "--fetch", "--json"))["result"]}
    assert (fetched[module.root.as_posix()]["repository"], fetched[module.root.as_posix()]["remote"]) == (None, None)
    assert (fetched[parallel.as_posix()]["repository"], fetched[parallel.as_posix()]["remote"]) == ("tester/remote",
                                                                                                     "archived")
    parallel.rename(parallel.with_name("Moved"))      # ECOBuildの外で移動した
    assert "見つかりません" in cli("workspace", "list").output
    exists = {c["path"]: c["exists"] for c in as_json(cli("workspace", "list", "--json"))["result"]}
    assert exists == {module.root.as_posix(): True, parallel.as_posix(): False}


def test_old_clone_records_are_read(cli, module, monkeypatch):
    """以前の記録（clones.json。種類つき）は読み、次に書くときに workspaces.json へ移す。"""
    from ecobuild import workspaces
    old = workspaces.file().with_name(workspaces.OLD_FILE_NAME)
    workspaces.file().unlink(missing_ok=True)
    old.write_text(json.dumps({"clones": [{"path": module.root.as_posix(), "kind": "module"}]}), encoding="utf-8")
    assert [c["path"] for c in as_json(cli("workspace", "list", "--json"))["result"]] == [module.root.as_posix()]
    assert workspaces.forget(module.root) and not old.exists() and workspaces.recorded() == []


def test_close_workspace(cli, module, parallel, monkeypatch):
    """workspace close：場所ごと消して記録から外す。GitHubにないものがあれば止める（--discard-local で捨てる）。"""
    write(parallel / "local.txt", "x\n")
    stopped = as_json(cli("workspace", "close", "../Calc-1", "--json"))
    assert stopped["error"]["code"] == "unfinished_work" and parallel.exists()
    assert as_json(cli("workspace", "close", "../Calc-1", "--discard-local", "--json"))["error"]["code"] \
        == "confirmation_required"
    (parallel / "local.txt").unlink()
    preview = as_json(cli("workspace", "close", "../Calc-1", "--dry-run", "--json"))["result"]
    assert not preview["done"] and parallel.exists()
    output = cli("workspace", "close", "../Calc-1").output
    assert f"作業空間 {parallel} を閉じました" in output and not parallel.exists()
    assert [c["path"] for c in as_json(cli("workspace", "list", "--json"))["result"]] == [module.root.as_posix()]
    # タスクは開いたまま、GitHubのタスクブランチも残る（別の作業空間で再開できる）
    assert as_json(cli("task", "status", "1", "--json"))["result"]["remote"]


def test_close_workspace_with_another_inside(cli, module, monkeypatch):
    """中に別の作業空間（clone）があれば閉じない（新しいファイルとして見え、一緒に消えてしまうため）。"""
    from ecobuild.results import PrepareResult
    from ecobuild_cpp.type import CppType
    monkeypatch.setattr(CppType, "prepare", lambda self: PrepareResult((), False))
    assert cli("task", "new", "中で並行作業").exit_code == 0
    assert cli("task", "start", "1", "--dir", "inner/Calc-1").exit_code == 0
    monkeypatch.chdir(module.root)
    stopped = as_json(cli("workspace", "close", "--json"))
    assert stopped["error"]["code"] == "unfinished_work" and (module.root / "inner" / "Calc-1" / ".git").exists()


def test_close_workspace_in_use(cli, module, parallel, monkeypatch):
    """他のプログラムが使っていて動かせなければ、消せるものだけを消して、残ったものを知らせる。"""
    from pathlib import Path
    real = Path.rename

    def held(self, target):
        if self == parallel:
            raise PermissionError("使用中")
        return real(self, target)
    monkeypatch.setattr(Path, "rename", held)
    result = as_json(cli("workspace", "close", "../Calc-1", "--json"))["result"]
    assert not result["removed"] and parallel.is_dir() and not any(parallel.iterdir())
    assert [c["path"] for c in as_json(cli("workspace", "list", "--json"))["result"]] == [module.root.as_posix()]


def test_finish_can_close_workspace(cli, module, parallel, monkeypatch):
    """task finish --close-workspace：完了したら、その作業空間を閉じる（ほかのタスクの作業空間では使えない）。"""
    wrong = as_json(cli("task", "finish", "1", "--close-workspace", "--json"))
    assert wrong["error"]["code"] == "invalid_argument"
    monkeypatch.chdir(parallel)
    write(parallel / "a.txt", "a\n")
    assert cli("task", "commit", "--message", "a を追加", "a.txt").exit_code == 0
    result = as_json(cli("task", "finish", "--close-workspace", "--json"))["result"]
    assert result["closed_workspace"]["path"] == parallel.as_posix() and not parallel.exists()
    monkeypatch.chdir(module.root)
    assert [c["path"] for c in as_json(cli("workspace", "list", "--json"))["result"]] == [module.root.as_posix()]


def test_delete_removes_every_clone(cli, module, parallel, may_delete, monkeypatch):
    """--remove-workspaces：このPCに記録した作業空間すべて。どれか1つにでもGitHubにないものがあれば止める。"""
    github = module.repository.github
    assert cli("module", "archive", "tester/remote", "--yes").exit_code == 0
    write(parallel / "local.txt", "x\n")
    stopped = as_json(cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--remove-workspaces", "--json"))
    assert stopped["error"]["code"] == "unfinished_work" and github.deleted_repositories == []
    assert any(str(parallel) in item for item in stopped["error"]["details"])
    (parallel / "local.txt").unlink()
    # 他のプログラムが使っている clone は動かせない：GitHubのリポジトリも消さずに止め、clone はそのまま残る
    from pathlib import Path
    real = Path.rename

    def held(self, target):
        if self == parallel:
            raise PermissionError("使用中")
        return real(self, target)
    monkeypatch.setattr(Path, "rename", held)
    in_use = as_json(cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--remove-workspaces", "--json"))
    assert in_use["error"]["code"] == "in_use" and github.deleted_repositories == []
    assert parallel.is_dir() and (module.root / ".git").exists() and (parallel / ".git").exists()
    assert not list(module.root.parent.glob(".*.deleting*"))    # 先に移したものも元に戻した
    monkeypatch.setattr(Path, "rename", real)
    output = cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--remove-workspaces").output
    assert f"作業空間 {parallel} を削除しました" in output and not parallel.exists()
    assert as_json(cli("workspace", "list", "--json"))["result"] == []


def test_delete_discards_local_work_when_asked(cli, module, parallel, may_delete):
    """--discard-local：GitHubにない変更があっても、作業空間ごと削除する（--remove-workspaces と一緒にだけ）。"""
    assert cli("module", "archive", "tester/remote", "--yes").exit_code == 0
    write(parallel / "local.txt", "x\n")
    alone = as_json(cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--discard-local", "--json"))
    assert alone["error"]["code"] == "invalid_argument" and parallel.exists()
    asked = as_json(cli("module", "delete", "tester/remote", "--remove-workspaces", "--discard-local", "--json"))
    assert asked["error"]["code"] == "confirmation_required" and "それらごと削除します" in asked["error"]["message"]
    result = as_json(cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--remove-workspaces",
                         "--discard-local", "--json"))["result"]
    assert result["workspace_removed"] and not parallel.exists() and not module.root.exists()


def test_delete_removes_every_clone_as_json(cli, module, parallel, may_delete):
    assert cli("module", "archive", "tester/remote", "--yes").exit_code == 0
    result = as_json(cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--remove-workspaces",
                         "--json"))["result"]
    assert sorted(result["removed"]) == sorted([module.root.as_posix(), parallel.as_posix()])
    assert result["workspace_removed"] and not module.root.exists() and not parallel.exists()
    assert as_json(cli("workspace", "list", "--json"))["result"] == []


def test_errors_from_repository_changed_on_github(cli, module, monkeypatch):
    """git・gh の失敗が、GitHubでのアーカイブ・削除のためなら、そう分かるエラーと案内にする。"""
    from ecowork.errors import WorkError
    from ecobuild.errors import ErrorCode

    def failing(output):
        def fail(*args, **kwargs):
            raise WorkError(ErrorCode.GIT_ERROR, "git push に失敗しました。", details=output)
        return fail

    original = type(module.repository).status
    monkeypatch.setattr(type(module.repository), "status", failing(
        "remote: This repository was archived so it is read-only.\nfatal: unable to access"))
    archived = as_json(cli("status", "--json"))["error"]
    assert archived["code"] == "repository_archived" and "module unarchive" in archived["hint"]
    monkeypatch.setattr(type(module.repository), "status", failing("remote: Repository not found."))
    gone = as_json(cli("status", "--json"))["error"]
    assert gone["code"] == "repository_not_found" and "module list" in gone["hint"]

    module.repository.github.archived_repositories.append("tester/remote")
    monkeypatch.setattr(type(module.repository), "status", original)
    assert "アーカイブ（読み取り専用）されています" in cli("status", "--fetch").output


def test_restored_module_reopens_its_task_data(cli, module, may_delete):
    """削除したリポジトリをGitHubで戻したら、閉じたタスク管理の情報を開き直して使う（作り直さない）。"""
    github = module.repository.github
    assert cli("task", "new", "t").exit_code == 0
    assert cli("task", "edit", "1", "--priority", "High").exit_code == 0
    assert cli("module", "archive", "tester/remote", "--yes").exit_code == 0
    assert cli("module", "delete", "tester/remote", "--confirm", "tester/remote").exit_code == 0
    board = github.ecobuild_board()
    github.link_board(module.root, board.id, link=False)          # 戻したリポジトリにはリンクがない
    github.archived_repositories.clear()
    assert cli("task", "new", "戻した").exit_code == 0
    assert len(github.boards) == 1 and not github.ecobuild_board().closed
    assert as_json(cli("task", "list", "--json"))["result"][0]["priority"] == "High"


def test_delete_module_with_clone(cli, module, may_delete):
    """--remove-workspaces：手元にだけあるもの（GitHubにないコミット等）があれば、何も消さずに止める。"""
    github = module.repository.github
    assert cli("module", "archive", "tester/remote", "--yes").exit_code == 0
    write(module.root / "local.txt", "x\n")
    git(module.root, "add", "local.txt")
    git(module.root, "commit", "--quiet", "-m", "手元だけ")
    stopped = as_json(cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--remove-workspaces", "--json"))
    assert stopped["error"]["code"] == "unfinished_work" and github.deleted_repositories == []
    git(module.root, "push", "--quiet", "origin", "main")
    result = as_json(cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--remove-workspaces", "--json"))["result"]
    assert result["workspace_removed"] and not module.root.exists()
    assert github.deleted_repositories == ["tester/remote"]


def test_delete_refuses_non_modules_and_missing_permission(cli, module, monkeypatch):
    from ecobuild_bundle import tooling
    github = module.repository.github
    github.archived_repositories.append("tester/remote")
    monkeypatch.setattr(tooling, "gh_has_scope", lambda scope: False)
    assert as_json(cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--json"))["error"]["code"] \
        == "github_permission"
    monkeypatch.setattr(github, "repository_has_file", lambda name, path: False)
    assert as_json(cli("module", "archive", "tester/remote", "--yes", "--json"))["error"]["code"] == "not_in_module"
    assert as_json(cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--json"))["error"]["code"] \
        == "not_in_module"
    assert github.deleted_repositories == []


def test_delete_finds_clone_made_by_new(cli, module, may_delete, tmp_path, monkeypatch):
    """new と同じく、今いるディレクトリの <名前> のcloneも見つける（所有者を省いた名前でも）。"""
    parent = tmp_path / "modules"
    parent.mkdir()
    git(parent, "clone", "--quiet", str(module.repository.github.bare), "remote")
    monkeypatch.chdir(parent)
    assert cli("module", "archive", "remote", "--yes").exit_code == 0
    result = as_json(cli("module", "delete", "remote", "--confirm", "tester/remote", "--remove-workspaces", "--json"))["result"]
    assert result["workspace_removed"] and not (parent / "remote").exists()


def test_files_made_by_ecobuild_are_always_committed(cli, module):
    """ECOBuildのコマンド（file add 等）が作ったファイルは、管理するファイルの対象外でもコミットに含める。"""
    from ecobuild.results import FilesChanged
    assert cli("task", "new", "作る", "--start").exit_code == 0
    write(module.root / "made.txt", "x\n")
    write(module.root / "other.txt", "y\n")
    module._created(FilesChanged("file add", ("made.txt",)))
    result = module.commit("作ったもの")
    assert result.files == ("made.txt",) and result.skipped == ("other.txt",)
    assert module._created_files() == set()


def test_team_commands(cli, module):
    """複数人での開発：他の人のタスクは引き継いでから始める。共同作業者とブランチの保護はコマンドで。"""
    github = module.repository.github
    assert cli("task", "new", "他の人の", "--assignee", "alice").exit_code == 0
    refused = as_json(cli("task", "start", "1", "--json"))
    assert refused["error"]["code"] == "task_assigned_to_other" and refused["error"]["details"] == ["alice"]
    taken = cli("task", "start", "1", "--take-over")
    assert taken.exit_code == 0 and "alice から引き継ぎました" in taken.output

    invited = cli("module", "members", "add", "bob")
    assert invited.exit_code == 0 and "招待しました" in invited.stdout
    assert "招待中" in cli("module", "members").stdout and "bob（書き込み）" in cli("module", "members").stdout
    github.accept_invitation("bob")
    assert [m["login"] for m in as_json(cli("module", "members", "--json"))["result"]] == ["bob"]
    assert as_json(cli("module", "members", "remove", "bob", "--json"))["error"]["code"] == "confirmation_required"
    assert cli("module", "members", "remove", "bob", "--yes").exit_code == 0

    assert "ブランチの保護はありません" in cli("module", "protect", "--show").stdout
    protected = as_json(cli("module", "protect", "--approvals", "1", "--yes", "--json"))
    assert protected["result"]["approvals"] == 1 and "require_approval" in " ".join(protected["notices"])
    assert "承認 1 人" in cli("module", "protect", "--show").stdout
    assert cli("module", "protect", "--show", "--off").exit_code == 2
    assert "外しました" in cli("module", "protect", "--off", "--yes").stdout
    github.free_private = True
    assert as_json(cli("module", "protect", "--yes", "--json"))["error"]["code"] == "plan_required"


def test_agent_starts_at_the_workspace_root(cli, module, monkeypatch):
    import ecoagent
    started = []
    monkeypatch.setattr(ecoagent, "start", lambda directory, command: started.append((directory, command))
                        or ecoagent.Session(1, tuple(command), directory))
    assert as_json(cli("agent", "start", "--json"))["error"]["code"] == "not_on_task_branch"   # タスクブランチでだけ起動する
    assert started == []

    cli("task", "new", "AIで作業", "--start")
    assert as_json(cli("agent", "start", "--json"))["ok"]
    assert started == [(module.root, ecoagent.DEFAULT_COMMAND)]
    (module.root / "sub").mkdir()
    monkeypatch.chdir(module.root / "sub")
    result = as_json(cli("agent", "start", "--agent", "codex --full-auto", "--json"))["result"]
    assert started[-1] == (module.root, ["codex", "--full-auto"])
    assert result["command"] == ["codex", "--full-auto"]
    cli("agent", "start")
    assert started[-1] == (module.root, ecoagent.DEFAULT_COMMAND)


def test_container(cli, module):
    """作業空間をコンテナにするかは、このPCの ecobuild.local.toml に持つ（コミットしない）。Docker は使えないものとする。"""
    shown = as_json(cli("container", "status", "--json"))["result"]
    assert not shown["container"] and not shown["changed"]
    assert as_json(cli("container", "start", "--json"))["error"]["code"] == "container_error"   # コンテナにしていない
    chosen = as_json(cli("container", "on", "--json"))["result"]
    assert chosen["container"] and chosen["changed"] and not chosen["docker_ready"]
    assert "container = true" in (module.root / ".ecobuild/ecobuild.local.toml").read_text(encoding="utf-8")
    assert "setup --docker" in cli("container", "status").output
    failed = as_json(cli("container", "start", "--json"))["error"]
    assert failed["code"] == "container_error" and "setup --docker" in failed["hint"]
    assert as_json(cli("container", "off", "--json"))["result"]["changed"]
    assert "container" not in (module.root / ".ecobuild/ecobuild.local.toml").read_text(encoding="utf-8")
