import json
from pathlib import Path

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

    invoke.chdir = monkeypatch.chdir
    return invoke


def as_json(result):
    return json.loads(result.stdout)


def start(cli, *args) -> Path:
    """作業空間を作るコマンド（task start・task new --start）を流して、その作業空間へ移る。作業空間の場所を返す。"""
    document = as_json(cli(*args, "--json"))
    assert document["ok"], document
    result = document["result"]
    place = Path((result.get("task_branch") or result)["workspace"])
    cli.chdir(place)
    return place


def test_every_command_has_help():
    runner = CliRunner()
    for args in (["module", "new"], ["module", "clone"], ["module", "types"], ["module", "list"], ["module", "show"],
                 ["workspace", "list"], ["workspace", "add"], ["workspace", "forget"], ["workspace", "close"],
                 ["container", "status"], ["container", "on"], ["container", "off"], ["container", "start"],
                 ["container", "stop"], ["container", "remove"], ["container", "dockerfile"],
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
                 ["unlink"], ["workspace", "create"], ["workspace", "path"]):
        assert runner.invoke(build_cli(), [*args, "--help"]).exit_code == 2, args
    shown = runner.invoke(build_cli(), ["task", "--help"]).output
    assert shown.index("コマンド（計画）:") < shown.index("コマンド（作業）:") < shown.index("コマンド（提出と完了）:")


def test_cli_full_cycle(cli, module):
    required = as_json(cli("task", "new", "0除算対策", "--start", "--json"))   # タスクブランチの名前は必須
    assert required["error"]["code"] == "branch_name_required"
    assert as_json(cli("task", "list", "--json"))["result"] == []              # Issueを作る前に止める
    result = cli("task", "new", "0除算対策", "--start", "--name", "0除算対策", "--json")
    assert result.exit_code == 0
    document = as_json(result)
    assert document["ok"] and document["result"]["task_branch"]["branch"] == "task/1-0除算対策"
    assert "_module" not in document["result"]["task"]
    work = Path(document["result"]["task_branch"]["workspace"])       # 元の clone の中の作業空間。元の clone は main のまま
    assert work == module.root / ".ecobuild" / "w" / "1" and git(module.root, "branch", "--show-current") == "main"
    assert git(module.root, "status", "--porcelain") == ""             # 作業空間は元の clone の git に見えない
    cli.chdir(work)

    write(work / "calc.cpp", "int calc;\n")
    write(work / "notes.tmp", "メモ\n")          # 管理するファイルの対象外
    status = as_json(cli("status", "--json"))["result"]
    assert status["excluded"] == ["notes.tmp"]
    committed = as_json(cli("task", "commit", "--message", "計算を追加", "--json"))["result"]
    assert committed["branch"] == "task/1-0除算対策" and committed["files"] == ["calc.cpp"]
    assert committed["skipped"] == ["notes.tmp"]
    status = as_json(cli("status", "--json"))["result"]
    assert status["task"] == 1 and status["staged"] == [] and status["untracked"] == ["notes.tmp"]

    pr = as_json(cli("task", "submit", "--no-check", "--json"))["result"]
    assert pr["head"] == "task/1-0除算対策" and pr["base"] == "main"
    (work / "notes.tmp").unlink()                     # 対象外の新しいファイルが残っていれば、作業空間は消さない（失われる）
    finished = cli("task", "finish")                 # 作業空間の中で完了しても、作業空間ごと片付く
    assert finished.exit_code == 0 and "完了しました：#1 0除算対策" in finished.stdout
    assert f"作業空間 {work} を消しました" in finished.stdout and not work.exists()
    assert git(module.root, "branch", "--show-current") == "main"
    assert "task/1-0除算対策" not in git(module.root, "branch", "--list")
    assert cli("task", "prune").stdout.strip() == "片付けるタスクブランチはありません"


def test_commit_paths_and_track(cli, module):
    """パスを書けば対象外のファイルも含める。管理するファイルは ecobuild track で足せる。"""
    work = start(cli, "task", "new", "記録", "--start", "--name", "作業")
    write(work / "data" / "a.json", "{}\n")
    write(work / "b.json", "{}\n")
    nothing = as_json(cli("task", "commit", "--message", "x", "--json"))
    assert nothing["error"]["code"] == "nothing_to_commit" and "data/a.json" in nothing["error"]["hint"]
    chosen = as_json(cli("task", "commit", "data", "--message", "データ", "--json"))["result"]
    assert chosen["files"] == ["data/a.json"] and chosen["outside"] == ["data/a.json"]
    listed = as_json(cli("track", "--json"))["result"]
    assert {"pattern": "*.cpp", "source": "type", "excluded": False} in listed["patterns"]
    assert cli("track", "add", "*.json").exit_code == 0
    assert 'include = ["*.json"]' in (work / ".ecobuild" / "ecobuild.toml").read_text(encoding="utf-8")
    committed = as_json(cli("task", "commit", "--message", "設定とデータ", "--json"))["result"]
    assert set(committed["files"]) == {"b.json", ".ecobuild/ecobuild.toml"}
    assert cli("track", "remove", "*.md").exit_code == 0
    assert 'exclude = ["*.md"]' in (work / ".ecobuild" / "ecobuild.toml").read_text(encoding="utf-8")
    assert as_json(cli("track", "remove", ".ecobuild/ecobuild.toml", "--json"))["error"]["code"] == "invalid_argument"
    write(work / "doc.md", "x\n")
    assert as_json(cli("status", "--json"))["result"]["excluded"] == ["doc.md"]


def test_task_reset_keep_leaves_the_changes_uncommitted(cli, module):
    """task reset --keep：コミットを取り消して変更を残す（ECOBuild のファイルの変更も、変更のまま）。"""
    work = start(cli, "task", "new", "取り消し", "--start", "--name", "作業")
    write(work / "a.txt", "a\n")
    assert cli("task", "commit", "a.txt", "--message", "a").exit_code == 0
    assert cli("track", "add", "*.json").exit_code == 0          # ecobuild.toml が変わる（コミットはしない）
    assert cli("task", "commit", "--message", "設定", "--json").exit_code == 0
    head = as_json(cli("log", "--count", "3", "--json"))["result"]
    assert head[0]["subject"] == "設定"
    reset = as_json(cli("task", "reset", head[1]["sha"] + "~1", "--keep", "--yes", "--json"))["result"]
    assert reset["kept"] and len(reset["dropped"]) == 2
    status = as_json(cli("status", "--json"))["result"]
    assert ".ecobuild/ecobuild.toml" in status["unstaged"] and "a.txt" in status["untracked"]
    assert as_json(cli("log", "--count", "1", "--json"))["result"][0]["sha"] == reset["commit"]   # コミットし直していない


def test_task_drop_confirms_lost_commits(cli, module):
    work = start(cli, "task", "new", "やめる作業", "--start", "--name", "作業")
    write(work / "a.txt", "a\n")
    assert cli("task", "add", "a.txt").exit_code == 0
    assert cli("task", "commit", "--message", "途中").exit_code == 0
    refused = cli("task", "drop", "--json")
    assert refused.exit_code == 1 and as_json(refused)["error"]["code"] == "confirmation_required"
    dropped = as_json(cli("task", "drop", "--close", "--yes", "--json"))["result"]
    assert dropped["lost_commits"] == ["途中"] and dropped["issue_closed"]
    assert dropped["workspace_removed"] == work.as_posix() and not work.exists() and dropped["switched_to"] is None
    human = cli("task", "drop")
    assert human.exit_code == 1  # もうタスクブランチにいない（元の clone へ出た）


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
    rows = {b["name"]: b for b in as_json(cli("branch", "list", "--json"))["result"]}
    assert rows["main"]["format"] == rows["main"]["latest_format"]   # 仕様の版も添える（GUI のブランチ画面が使う）


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
    as_json(cli("task", "new", "位置引数", "--start", "--name", "作業", "--json"))
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
    """task prune <番号>：開いているタスクなら、手元の写しだけを消す（以前の task remove）。作業空間も一緒に消える。"""
    work = start(cli, "task", "new", "手元を消す", "--start", "--name", "作業")
    write(work / "a.txt", "a\n")
    assert cli("task", "commit", "a.txt", "--message", "途中").exit_code == 0
    refused = as_json(cli("task", "prune", "1", "--json"))
    assert refused["error"]["code"] == "commits_would_be_lost"
    assert cli("task", "push").exit_code == 0
    removed = cli("task", "prune", "1")
    assert removed.exit_code == 0 and "ecobuild task start 1" in removed.stdout
    assert f"作業空間 {work} を消しました" in removed.stdout and not work.exists()
    assert "- #1" in cli("task", "list").stdout  # GitHubにだけある
    assert start(cli, "task", "start", "1") == work
    assert git(work, "branch", "--show-current") == "task/1-作業" and (work / "a.txt").exists()


def test_task_clean_without_targets(cli):
    result = cli("task", "prune")
    assert result.exit_code == 0 and "片付けるタスクブランチはありません" in result.stdout


def test_task_labels_assignees_and_comments(cli, module):
    start(cli, "task", "new", "落ちる", "--label", "bug,urgent", "--start", "--name", "作業")
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
    shown = as_json(cli("ci", "show", "--json"))["result"]
    assert (shown["exists"], shown["configurations"]) == (False, ["Debug"]) and "ワークフロー" in cli("ci", "show").stdout


def test_draft_submission_can_be_made_ready(cli, module):
    """下書きの提出は完了できず、案内される ecobuild task submit で解除してから完了できる。"""
    work = start(cli, "task", "new", "下書き", "--start", "--name", "作業")
    write(work / "a.cpp", "a\n")
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


def test_finish_follows_the_submission_unless_told(cli, module):
    """閉じるかは提出で決める：中間提出を task finish すると続ける。--complete／--partial で変えられる。"""
    work = start(cli, "task", "new", "続ける", "--start", "--name", "作業")
    write(work / "a.cpp", "a\n")
    cli("task", "commit", "--message", "a")
    assert as_json(cli("task", "submit", "--partial", "--no-check", "--json"))["result"]["partial"]
    assert as_json(cli("task", "submit", "--partial", "--complete", "--json"))["error"]["code"] == "invalid_argument"
    first = as_json(cli("task", "finish", "--json"))["result"]
    assert first["partial"] and first["closed_issue"] is None and work.exists()   # 中間提出：作業空間は残る
    write(work / "b.cpp", "b\n")
    cli("task", "commit", "--message", "b")
    assert as_json(cli("task", "submit", "--partial", "--no-check", "--json"))["result"]["partial"]
    assert not as_json(cli("task", "submit", "--complete", "--no-check", "--json"))["result"]["partial"]
    assert as_json(cli("task", "finish", "--json"))["result"]["closed_issue"] == 1


def test_submit_refuses_uncommitted_changes(cli, module):
    work = start(cli, "task", "new", "未記録", "--start", "--name", "作業")
    write(work / "a.cpp", "a\n")
    refused = as_json(cli("task", "submit", "--no-check", "--json"))
    assert refused["error"]["code"] == "dirty_working_tree" and refused["error"]["details"] == ["a.cpp"]
    write(work / "ignored.tmp", "x\n")       # 管理しないファイルは止めない
    cli("task", "commit", "--message", "a")
    assert cli("task", "submit", "--no-check").exit_code == 0


def test_review_approve_and_reject_from_cli(cli, module):
    """番号はタスクの番号。自分の提出は承認できず、task finish を案内する。確認は確認用の作業空間（.ecobuild/w/r<PR>）で。"""
    from dataclasses import replace
    work = start(cli, "task", "new", "見てもらう", "--start", "--name", "作業")
    write(work / "a.cpp", "a\n")
    cli("task", "commit", "--message", "a")
    cli("task", "submit", "--no-check")
    own = as_json(cli("task", "approve", "1", "--json"))
    assert own["error"]["code"] == "own_pull_request" and "task finish 1" in own["error"]["hint"]
    github = module.repository.github
    number = module.repository.submission(1).number
    github.pulls[number] = replace(github.pulls[number], author="someone")
    cli.chdir(module.root)
    assert cli("task", "reject", "1").exit_code == 2         # 理由がない
    assert "#1 を差し戻しました" in cli("task", "reject", "1", "--message", "直して").stdout
    reviewed = cli("task", "review", "1")
    review = module.root / ".ecobuild" / "w" / f"r{number}"
    assert reviewed.exit_code == 0 and "task approve 1" in reviewed.stdout and str(review) in reviewed.stdout
    assert git(module.root, "branch", "--show-current") == "main"      # 元の clone は切り替えない
    listed = as_json(cli("workspace", "list", "--json"))["result"]["modules"][0]["workspaces"]
    assert {(w["name"], w["review"]) for w in listed} == {("1", None), (f"r{number}", number)}
    cli.chdir(review)
    assert "#1 の提出を確認中" in cli("status").stdout
    approved = cli("task", "approve", "1", "--message", "よい")
    assert approved.exit_code == 0 and "承認して完了しました：#1" in approved.stdout
    assert f"確認用の作業空間 {review} を消しました" in approved.stdout and f"作業空間 {work} を消しました" in approved.stdout
    assert not review.exists() and not work.exists()
    assert git(module.root, "branch", "--show-current") == "main" and "task/1-作業" not in git(module.root, "branch")


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
    def work(place, name):
        write(place / name, name + "\n")
        assert cli("task", "commit", name, "--message", name).exit_code == 0

    assert cli("task", "new", "親").exit_code == 0
    assert cli("task", "new", "子", "--parent", "1").exit_code == 0
    assert as_json(cli("task", "start", "2", "--name", "子", "--base", "main", "--json"))["error"]["code"] == "invalid_base"
    started = cli("task", "start", "2", "--name", "子")
    assert started.exit_code == 0 and "作成元 task/1-親" in started.output and "task/1-親 をGitHubに作りました" in started.output
    child = module.root / ".ecobuild" / "w" / "2"
    cli.chdir(child)
    work(child, "child.txt")
    pr = as_json(cli("task", "submit", "--no-check", "--json"))["result"]
    assert pr["base"] == "task/1-親"
    finished = as_json(cli("task", "finish", "--json"))["result"]
    assert finished["closed_issue"] == 2 and finished["workspace_removed"] == child.as_posix() and not child.exists()

    assert cli("task", "new", "子2", "--parent", "1").exit_code == 0
    parent = start(cli, "task", "start", "1")
    assert (parent / "child.txt").exists()
    work(parent, "parent.txt")
    submitted = cli("task", "submit", "--no-check")
    assert submitted.exit_code == 0 and "子タスクが終わるまで完了できません" in submitted.output
    refused = as_json(cli("task", "finish", "--json"))
    assert refused["error"]["code"] == "open_subtasks" and "#4" in " ".join(refused["error"]["details"])   # PRとIssueは番号を共有（#3 は子のPR）
    assert as_json(cli("task", "close", "1", "--json"))["error"]["code"] == "open_subtasks"
    assert as_json(cli("task", "drop", "1", "--close", "--yes", "--json"))["error"]["code"] == "open_subtasks"

    closed = cli("task", "close", "4")                       # タスクブランチなしで閉じた子
    assert closed.exit_code == 0 and "子タスクはすべて閉じました" in closed.output and "task finish 1" in closed.output
    assert as_json(cli("task", "finish", "1", "--json"))["result"]["closed_issue"] == 1
    assert git(module.root, "branch", "--show-current") == "main" and not parent.exists()
    cli.chdir(module.root)
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
    """タスク #1 を作業空間（元の clone の中の .ecobuild/w/1）で始める。型の準備はしない。"""
    from ecobuild.results import PrepareResult
    from ecobuild_cpp.type import CppType
    monkeypatch.setattr(CppType, "prepare", lambda self: PrepareResult((), False))
    assert cli("task", "new", "並行作業").exit_code == 0
    place = start(cli, "task", "start", "1", "--name", "作業")
    monkeypatch.chdir(module.root)
    return place


def test_workspaces(cli, module, parallel, monkeypatch, tmp_path):
    """このPCのモジュールの一覧：元の clone と、その中の作業空間（タスクブランチのあるもの）。作業空間は一覧に入れない。"""
    listed = as_json(cli("workspace", "list", "--json"))["result"]
    assert [m["path"] for m in listed["modules"]] == [module.root.as_posix()] and listed["legacy"] == []
    entry = listed["modules"][0]
    assert (entry["branch"], entry["default_branch"], entry["task"]) == ("main", "main", None)
    assert [(w["name"], w["path"], w["branch"], w["task"], w["review"]) for w in entry["workspaces"]] == [
        ("1", parallel.as_posix(), "task/1-作業", 1, None)]
    assert "task/1-作業＝タスク #1" in cli("workspace", "list").output

    task = as_json(cli("task", "list", "--json"))["result"][0]
    assert task["workspace"] == parallel.as_posix() and task["task_branch"]   # ブランチは元の clone と共有
    assert "+ #1 並行作業" in cli("task", "list").output and f"（場所：{parallel}）" in cli("task", "list").output
    status = as_json(cli("task", "status", "1", "--json"))["result"]
    assert status["workspace"] == parallel.as_posix() == status["task"]["workspace"]
    assert "タスクブランチ：task/1-作業" in cli("task", "status", "1").output
    shown = as_json(cli("module", "show", "--json"))["result"]
    assert [c["path"] for c in shown["workspaces"]] == [parallel.as_posix()]
    assert "このPCの作業空間" in cli("module", "show").output

    for command in ("add", "forget"):                 # 作業空間は元の clone から分かるので、一覧に入れない・外さない
        assert as_json(cli("workspace", command, ".ecobuild/w/1", "--json"))["error"]["code"] == "invalid_argument"
    assert as_json(cli("workspace", "forget", ".", "--json"))["result"]["exists"]
    assert as_json(cli("workspace", "list", "--json"))["result"]["modules"] == []
    assert as_json(cli("workspace", "forget", ".", "--json"))["error"]["code"] == "workspace_not_recorded"
    monkeypatch.chdir(parallel)                       # 作業空間の中で使うと、元の clone が一覧に入る
    assert cli("status").exit_code == 0
    assert [m["path"] for m in as_json(cli("workspace", "list", "--json"))["result"]["modules"]] == [module.root.as_posix()]
    monkeypatch.chdir(module.root)
    nested = module.root / "deps" / "Base"            # 依存先のclone 等、他のモジュールの中のものは記録しない
    write(nested / ".ecobuild" / "ecobuild.toml", "")
    assert as_json(cli("workspace", "add", "deps/Base", "--json"))["error"]["code"] == "invalid_argument"

    git(module.root, "switch", "--quiet", "-c", "other")   # 元の clone が既定のブランチにいなければ知らせる
    noticed = as_json(cli("workspace", "list", "--json"))
    assert any("既定のブランチ main に戻してください" in n for n in noticed["notices"])
    git(module.root, "switch", "--quiet", "main")

    git(module.root, "remote", "set-url", "origin", "https://github.com/tester/remote.git")
    module.repository.github.archived_repositories.append("tester/remote")
    fetched = as_json(cli("workspace", "list", "--fetch", "--json"))["result"]["modules"][0]
    assert (fetched["repository"], fetched["remote"]) == ("tester/remote", "archived")
    monkeypatch.chdir(tmp_path)
    module.root.rename(module.root.with_name("Moved"))   # ECOBuildの外で移動した
    assert "見つかりません" in cli("workspace", "list").output
    exists = {c["path"]: c["exists"] for c in as_json(cli("workspace", "list", "--json"))["result"]["modules"]}
    assert exists == {module.root.as_posix(): False}


def test_default_branch_comes_from_branches_table(tmp_path):
    """元の clone の既定のブランチは ecobuild.toml の [branches] default_base（config.load と同じ）。[module] ではない。"""
    from ecobuild import workspaces
    module = 'format = 3\n\n[module]\nname = "X"\ntype = "python"\n'
    write(tmp_path / ".ecobuild" / "ecobuild.toml", module + '\n[branches]\ndefault_base = "feature/mvp"\n')
    assert workspaces._default_branch(tmp_path) == "feature/mvp"
    write(tmp_path / ".ecobuild" / "ecobuild.toml", module)
    assert workspaces._default_branch(tmp_path) == "main"


def test_old_records_move_to_the_module_list(cli, module, parallel, tmp_path):
    """以前の記録（workspaces.json・clones.json）は読むだけ：modules.json がなければ移す。同じリポジトリの clone が
    2つ以上あれば1つを元の clone にし（.ecobuild/ の外 → フォルダー名がリポジトリ名 → タスクブランチにいない）、残りと
    ほかのモジュールの .ecobuild/ の中のもの（前の版の作業役）は前の版の作業空間（legacy）にする。作業空間は飛ばす。"""
    from ecobuild import workspaces
    remote = module.repository.github.bare
    other = tmp_path / "Calc-2"                        # 前の版の作業空間（タスクブランチにいる）
    git(tmp_path, "clone", "--quiet", str(remote), str(other))
    git(other, "switch", "--quiet", "-c", "task/9-前の作業")
    team = module.root / ".ecobuild" / "ai" / "team" / "2-作業役"
    git(tmp_path, "clone", "--quiet", str(remote), str(team))
    old = workspaces.file().with_name("workspaces.json")
    recorded = [other, module.root, parallel, team, tmp_path / "なくなった"]
    text = json.dumps({"workspaces": [{"path": p.as_posix()} for p in recorded]})
    old.write_text(text, encoding="utf-8")
    workspaces.file().unlink(missing_ok=True)
    listed = as_json(cli("workspace", "list", "--json"))["result"]
    assert [(m["path"], m["exists"]) for m in listed["modules"]] == [(module.root.as_posix(), True),
                                                                     ((tmp_path / "なくなった").as_posix(), False)]
    assert sorted(entry["path"] for entry in listed["legacy"]) == sorted([other.as_posix(), team.as_posix()])
    assert "前の版の作業空間" in cli("workspace", "list").output
    assert old.read_text(encoding="utf-8") == text and workspaces.file().is_file()   # 以前の記録はそのまま
    data = json.loads(workspaces.file().read_text(encoding="utf-8"))
    assert data["version"] == 1 and {"path", "repository", "url"} <= set(data["modules"][0])
    workspaces.file().unlink()                         # 消せば、また移す
    assert len(as_json(cli("workspace", "list", "--json"))["result"]["legacy"]) == 2


def test_close_workspace(cli, module, parallel, monkeypatch):
    """workspace close：作業空間（git worktree）を場所ごと消す。GitHubにないものがあれば止める（--discard-local で捨てる）。
    元の clone は閉じられない。"""
    write(parallel / "local.txt", "x\n")
    stopped = as_json(cli("workspace", "close", ".ecobuild/w/1", "--json"))
    assert stopped["error"]["code"] == "unfinished_work" and parallel.exists()
    assert as_json(cli("workspace", "close", ".ecobuild/w/1", "--discard-local", "--json"))["error"]["code"] \
        == "confirmation_required"
    (parallel / "local.txt").unlink()
    preview = as_json(cli("workspace", "close", ".ecobuild/w/1", "--dry-run", "--json"))["result"]
    assert not preview["done"] and parallel.exists()
    output = cli("workspace", "close", ".ecobuild/w/1").output
    assert f"作業空間 {parallel} を閉じました" in output and not parallel.exists()
    assert len(git(module.root, "worktree", "list").splitlines()) == 1     # git の記録も片付けた
    assert as_json(cli("workspace", "list", "--json"))["result"]["modules"][0]["workspaces"] == []
    # タスクは開いたまま、タスクブランチも残る（task start で同じ場所に作り直せる）
    assert as_json(cli("task", "status", "1", "--json"))["result"]["remote"]
    assert start(cli, "task", "start", "1") == parallel
    monkeypatch.chdir(module.root)
    refused = as_json(cli("workspace", "close", "--json"))   # 元の clone
    assert refused["error"]["code"] == "invalid_argument" and module.root.exists()


def test_close_workspace_in_use(cli, module, parallel, monkeypatch):
    """他のプログラムが使っていて動かせなければ、何も消さずに断る（git の記録が残るので、途中まで消さない）。"""
    real = Path.rename

    def held(self, target):
        if self == parallel:
            raise PermissionError("使用中")
        return real(self, target)
    monkeypatch.setattr(Path, "rename", held)
    refused = as_json(cli("workspace", "close", ".ecobuild/w/1", "--json"))
    assert refused["error"]["code"] == "in_use" and (parallel / ".git").is_file()
    assert "locked" in git(module.root, "worktree", "list", "--porcelain")   # ロックも戻した


def test_finish_removes_the_workspace(cli, module, parallel, monkeypatch):
    """task finish：タスクブランチと一緒に作業空間も消す（作業空間の中で実行しても。外へ出てから消す）。
    管理するファイルに当たる新しいファイルがあれば、作業空間とタスクブランチは残して知らせる。"""
    assert cli("task", "finish", "1", "--close-workspace", "--json").exit_code == 2   # いつも消すので、オプションはない
    monkeypatch.chdir(parallel)
    write(parallel / "a.txt", "a\n")
    assert cli("task", "commit", "--message", "a を追加", "a.txt").exit_code == 0
    result = as_json(cli("task", "finish", "--json"))["result"]
    assert result["workspace_removed"] == parallel.as_posix() and not parallel.exists()
    assert Path.cwd().resolve() == module.root.resolve()
    assert as_json(cli("workspace", "list", "--json"))["result"]["modules"][0]["workspaces"] == []

    number = str(as_json(cli("task", "new", "残す", "--json"))["result"]["task"]["number"])
    kept = start(cli, "task", "start", number, "--name", "残す")
    write(kept / "b.cpp", "b\n")
    assert cli("task", "commit", "b.cpp", "--message", "b").exit_code == 0
    assert cli("task", "submit", "--no-check").exit_code == 0
    write(kept / "c.cpp", "c\n")                       # 管理するファイルに当たる、コミットしていない新しいファイル
    monkeypatch.chdir(module.root)                    # 元の clone から完了する（作業空間の中なら、完了の前に止まる）
    result = as_json(cli("task", "finish", number, "--json"))
    assert result["ok"] and result["result"]["workspace_kept"] and (kept / "c.cpp").exists()
    assert any("新しいファイル" in n for n in result["notices"])


def test_finish_tells_how_to_remove_a_kept_workspace(cli, module, parallel, monkeypatch):
    """作業空間を使用中で消せず残したら（作業空間の中のシェルから finish した等）、後で消す方法を案内する。"""
    from ecobuild.errors import EcoBuildError, ErrorCode
    from ecobuild_bundle import Module

    def in_use(cls, path, **options):
        raise EcoBuildError(ErrorCode.IN_USE, f"作業空間 {path} は、他のプログラムが使っているため消せません。")
    monkeypatch.setattr(Module, "close_workspace", classmethod(in_use))
    write(parallel / "a.txt", "a\n")
    git(parallel, "add", "a.txt")
    git(parallel, "commit", "--quiet", "-m", "a")
    git(parallel, "push", "--quiet")
    finished = cli("task", "finish", "1", "--no-wait")
    assert finished.exit_code == 0 and "作業空間を残しました" in finished.stdout and parallel.exists()
    assert "ecobuild task prune --task 1" in finished.stdout


def _dependency_with_local_work(workspace: Path) -> Path:
    """作業空間の中の依存先の clone（deps/<名前>）に、GitHubにないコミットを置く。"""
    lib = workspace / "deps" / "Lib"
    lib.mkdir(parents=True)
    git(lib, "init", "--quiet")
    write(lib / "x.txt", "x\n")
    git(lib, "add", "x.txt")
    git(lib, "commit", "--quiet", "-m", "依存先の作業")
    return lib


def test_drop_keeps_a_workspace_whose_dependency_clone_has_local_work(cli, module, parallel):
    """作業空間の中の依存先の clone（除外しているので作業空間の変更には見えない）に手元にだけあるものがあれば、
    作業空間を消さずに残して知らせる（依存先の作業を失わない）。"""
    lib = _dependency_with_local_work(parallel)
    dropped = as_json(cli("task", "drop", "1", "--yes", "--json"))
    assert dropped["ok"], dropped
    assert "GitHubにない" in dropped["result"]["workspace_kept"] and (lib / "x.txt").is_file()


def test_drop_keeps_a_workspace_with_new_files_out_of_management(cli, module, parallel):
    """管理するファイルの対象外の新しいファイル（未追跡で除外していない）があれば、作業空間ごと消さずに残して知らせる
    （黙って消すと失われる）。--discard なら今どおり消す。"""
    write(parallel / "memo.xyz", "書きかけ\n")
    dropped = as_json(cli("task", "drop", "1", "--yes", "--json"))
    assert dropped["ok"], dropped
    assert "新しいファイル" in dropped["result"]["workspace_kept"] and (parallel / "memo.xyz").is_file()
    assert "task/1-作業" in git(module.root, "branch", "--list")
    pruned = as_json(cli("task", "prune", "--task", "1", "--json"))     # prune も同じ
    assert "新しいファイル" in json.dumps(pruned, ensure_ascii=False) and (parallel / "memo.xyz").is_file(), pruned
    (parallel / "memo.xyz").unlink()
    assert as_json(cli("task", "prune", "--task", "1", "--json"))["ok"] and not parallel.exists()


def test_discarding_removes_new_files_out_of_management(cli, module, parallel):
    """捨てるとき（discard。確認用の作業空間を消す等）は、新しいファイルがあっても作業空間ごと消す（今どおり）。"""
    from ecobuild.module import _TypeHooks
    write(parallel / "memo.xyz", "書きかけ\n")
    assert _TypeHooks(module).remove_workspace(module.repository, parallel, discard=True) and not parallel.exists()


def test_finish_keeps_a_workspace_whose_dependency_clone_has_local_work(cli, module, parallel):
    """finish も同じ：作業空間とタスクブランチを残して知らせる（完了はする）。"""
    write(parallel / "a.txt", "a\n")
    git(parallel, "add", "a.txt")
    git(parallel, "commit", "--quiet", "-m", "a")
    git(parallel, "push", "--quiet")
    lib = _dependency_with_local_work(parallel)
    result = as_json(cli("task", "finish", "1", "--no-wait", "--json"))
    assert result["ok"], result
    assert "GitHubにない" in result["result"]["workspace_kept"] and (lib / "x.txt").is_file()
    assert "task/1-作業" in git(module.root, "branch", "--list")


def test_finish_leaves_a_worktree_made_by_hand(cli, module, parallel, tmp_path):
    """人が git worktree で作った作業ツリーがタスクブランチを取り出していれば、それは消さず、ブランチも残して
    知らせる（完了はする）。workspace close でも閉じない。"""
    write(parallel / "a.txt", "a\n")
    git(parallel, "add", "a.txt")
    git(parallel, "commit", "--quiet", "-m", "a")
    git(parallel, "push", "--quiet")
    git(module.root, "worktree", "remove", "--force", "--force", str(parallel))
    hand = tmp_path / "hand"
    git(module.root, "worktree", "add", "--quiet", str(hand), "task/1-作業")
    result = as_json(cli("task", "finish", "1", "--no-wait", "--json"))
    assert result["ok"], result
    assert "ECOBuild が作った作業空間ではない" in result["result"]["workspace_kept"] and hand.is_dir()
    assert "task/1-作業" in git(module.root, "branch", "--list")
    refused = as_json(cli("workspace", "close", str(hand), "--json"))
    assert refused["error"]["code"] == "invalid_argument" and hand.is_dir()


def test_delete_removes_every_clone(cli, module, parallel, may_delete, monkeypatch):
    """--remove-workspaces：このPCの元の clone（中の作業空間ごと）すべて。どれか1つにでもGitHubにないものがあれば止める。"""
    github = module.repository.github
    assert cli("module", "archive", "tester/remote", "--yes").exit_code == 0
    write(parallel / "local.txt", "x\n")
    stopped = as_json(cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--remove-workspaces", "--json"))
    assert stopped["error"]["code"] == "unfinished_work" and github.deleted_repositories == []
    assert any(".ecobuild/w/1" in item for item in stopped["error"]["details"])   # 中の作業空間も見る
    (parallel / "local.txt").unlink()
    # 他のプログラムが使っている clone は動かせない：GitHubのリポジトリも消さずに止め、clone はそのまま残る
    from pathlib import Path
    real = Path.rename

    def held(self, target):
        if self == module.root:
            raise PermissionError("使用中")
        return real(self, target)
    monkeypatch.setattr(Path, "rename", held)
    in_use = as_json(cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--remove-workspaces", "--json"))
    assert in_use["error"]["code"] == "in_use" and github.deleted_repositories == []
    assert parallel.is_dir() and (module.root / ".git").exists() and (parallel / ".git").exists()
    assert not list(module.root.parent.glob(".*.deleting*"))    # 先に移したものも元に戻した
    monkeypatch.setattr(Path, "rename", real)
    output = cli("module", "delete", "tester/remote", "--confirm", "tester/remote", "--remove-workspaces").output
    assert f"作業空間 {module.root} を削除しました" in output and not parallel.exists() and not module.root.exists()
    assert as_json(cli("workspace", "list", "--json"))["result"] == {"modules": [], "legacy": []}


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
    assert result["removed"] == [module.root.as_posix()]     # 作業空間は元の clone と一緒に消える
    assert result["workspace_removed"] and not module.root.exists() and not parallel.exists()
    assert as_json(cli("workspace", "list", "--json"))["result"] == {"modules": [], "legacy": []}


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
    work = start(cli, "task", "new", "作る", "--start", "--name", "作業")
    write(work / "made.txt", "x\n")
    write(work / "other.txt", "y\n")
    other = type(module).find(work, github=module.repository.github)
    other._created(FilesChanged("file add", ("made.txt",)))
    result = other.commit("作ったもの")
    assert result.files == ("made.txt",) and result.skipped == ("other.txt",)
    assert other._created_files() == set()


def test_team_commands(cli, module):
    """複数人での開発：他の人のタスクは引き継いでから始める。共同作業者とブランチの保護はコマンドで。"""
    github = module.repository.github
    assert cli("task", "new", "他の人の", "--assignee", "alice").exit_code == 0
    refused = as_json(cli("task", "start", "1", "--json"))
    assert refused["error"]["code"] == "task_assigned_to_other" and refused["error"]["details"] == ["alice"]
    taken = cli("task", "start", "1", "--take-over", "--name", "作業")
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
    import os
    import ecoagent
    from ecobuild_agent import inside
    started = []
    monkeypatch.setattr(ecoagent, "start", lambda directory, command, **_: started.append((directory, command))
                        or ecoagent.Session(os.getpid(), tuple(command), directory))
    monkeypatch.setattr(inside, "agent_launch", lambda root, agent, **_: (tuple(agent), None))   # コンテナの中の起動の代わり
    assert as_json(cli("agent", "start", "--as", "lead", "--json"))["error"]["code"] == "not_on_task_branch"   # タスクブランチでだけ
    assert started == []

    work = start(cli, "task", "new", "AIで作業", "--start", "--name", "作業")
    assert as_json(cli("agent", "start", "--json"))["error"]["code"] == "invalid_argument"          # 登録を指定する
    refused = as_json(cli("agent", "start", "--as", "worker", "--json"))["error"]                  # 人が起動しない登録
    assert refused["code"] == "invalid_argument" and "lead" in refused["hint"] and started == []
    first = as_json(cli("agent", "start", "--as", "lead", "--json"))["result"]
    assert "container = true" in (work / ".ecobuild/ecobuild.local.toml").read_text(encoding="utf-8")   # 自動でコンテナに
    (directory, command), = started                     # Claude Code には登録の文書と、専用の MCP サーバーを渡す
    assert directory == work and command[0] == "claude" and "--session-id" in command   # 会話を記録に書く
    assert first["registration"] == "lead" and first["task"]["number"] == 1 and first["kind"] == "owner"
    assert first["session"] == command[command.index("--session-id") + 1]
    from ecobuild_agent import agents
    from ecobuild_agent import status as agent_status
    folder = agents.load(first["id"]).folder            # エージェントの置き場所（中からは INSIDE/<ID>）
    guide = command[command.index("--append-system-prompt-file") + 1]
    assert guide == f"{agent_status.INSIDE}/{first['id']}/guide.md"
    text = (folder / "guide.md").read_text(encoding="utf-8")
    assert "## あなたの役：進行役" in text and "ecobuild build" not in text   # 登録の文書。CLI の手順（agent guide）は渡さない
    assert command[command.index("--mcp-config") + 1].endswith(f"/{first['id']}/mcp.json") and "--strict-mcp-config" in command
    server = json.loads((folder / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["ecobuild"]
    assert server["args"][:4] == ["agent", "mcp", "--agent", first["id"]]
    settings_file = command[command.index("--settings") + 1].rsplit("/", 1)[-1]
    settings = json.loads((folder / settings_file).read_text(encoding="utf-8"))
    assert settings["hooks"]["Stop"][0]["hooks"][0]["command"].endswith("replied deliver")   # 新しい画面：受け箱はフックが届ける
    guard = settings["hooks"]["PreToolUse"]                                               # 書ける場所は絞らない
    assert guard == [{"matcher": "Bash", "hooks": [{"type": "command", "command": "ecobuild agent guard"}]}]   # シェルの関所だけ
    started.clear()
    (work / "sub").mkdir()
    monkeypatch.chdir(work / "sub")
    second = as_json(cli("agent", "start", "--as", "lead", "--program", "codex --full-auto", "--json"))["result"]
    assert started[-1] == (work, ("codex", "--full-auto"))      # Claude Code でなければ何も足さない
    assert second["id"] != first["id"]                                 # 同じ作業空間に2人目
    again = as_json(cli("agent", "start", "--program", f"claude --resume {first['session']}", "--json"))["result"]
    assert again["id"] == first["id"] and started[-1][1][:3] == ("claude", "--resume", first["session"])   # 会話で記録を引く
    # 記録のない会話・Claude Code の一覧で選ぶ（値なしの --resume）は、--as の登録で起動する（なければ分かる誤り）
    for program in ("claude --resume", "claude --resume no-record"):
        refused = as_json(cli("agent", "start", "--program", program, "--json"))["error"]
        assert refused["code"] == "invalid_argument" and "--as" in refused["message"]
    other = as_json(cli("agent", "start", "--as", "lead", "--program", "claude --resume no-record", "--json"))["result"]
    assert other["id"] not in (first["id"], second["id"]) and other["registration"] == "lead"
    # コンテナの中の MCP サーバーには、このPCで解決した登録を写して渡す（中には登録がない）
    assert "--registration-file" in server["args"]
    assert json.loads((folder / "registration.json").read_text(encoding="utf-8"))["name"] == "lead"


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


def test_container_dockerfile(cli, module, tmp_path):
    """イメージのエディター：環境の Dockerfile を読む（どのブランチでも）・書く（タスクブランチでだけ。--write <ファイル|->）。"""
    path = module.root / ".ecobuild/container/Dockerfile"
    shown = as_json(cli("container", "dockerfile", "--json"))["result"]
    assert not shown["exists"] and shown["text"].startswith("# ") and "FROM " in shown["text"]   # まだなければ型のひな型
    assert shown["environment"].endswith(":" + shown["hash"]) and shown["image"].startswith("ecobuild-calc:")
    assert not shown["editable"] and "タスクブランチ" in shown["reason"] and not shown["docker_ready"]
    assert "型のひな型" in cli("container", "dockerfile").output
    edited = tmp_path / "Dockerfile.new"
    edited.write_text("FROM ubuntu:24.04\nRUN echo lint\n", encoding="utf-8")
    refused = as_json(cli("container", "dockerfile", "--write", str(edited), "--json"))["error"]
    assert refused["code"] == "not_on_task_branch" and "task start" in refused["hint"] and not path.exists()

    path = start(cli, "task", "new", "解析ツール", "--start", "--name", "lint") / ".ecobuild/container/Dockerfile"
    assert as_json(cli("container", "dockerfile", "--json"))["result"]["editable"]
    wrote = as_json(cli("container", "dockerfile", "--write", str(edited), "--json"))["result"]
    assert wrote["changed"] and wrote["exists"] and wrote["hash"] != shown["hash"] and wrote["editable"]
    assert path.read_text(encoding="utf-8") == "FROM ubuntu:24.04\nRUN echo lint\n"
    piped = CliRunner().invoke(build_cli(), ["container", "dockerfile", "--write", "-"], input="FROM debian:12\n")
    assert piped.exit_code == 0 and "書きました" in piped.output and "task commit" in piped.output
    assert path.read_text(encoding="utf-8") == "FROM debian:12\n"
    assert "同じ中身" in CliRunner().invoke(build_cli(), ["container", "dockerfile", "--write", "-"], input="FROM debian:12").output
    missing = as_json(cli("container", "dockerfile", "--write", str(tmp_path / "none"), "--json"))["error"]
    assert missing["code"] == "file_not_found"
    assert as_json(cli("container", "recipe", "--json"))["result"]["dockerfile"] == "FROM debian:12\n"   # 試しに作る元


def test_pipelines_are_made_and_put_with_the_cli(cli, module):
    """パイプラインは既定でなし。pipeline add・on はタスクブランチで、on --local はどこでも。run で単体で走らせる。"""
    assert as_json(cli("pipeline", "list", "--json"))["result"] == {"pipelines": [], "triggers": {}, "local": {}}
    assert "パイプラインはありません" in cli("pipeline", "list").stdout
    refused = as_json(cli("pipeline", "add", "quick", "--steps", "generated", "--json"))
    assert refused["error"]["code"] == "not_on_task_branch"
    start(cli, "task", "new", "パイプラインの設定", "--start", "--name", "作業")
    made = as_json(cli("pipeline", "add", "quick", "--steps", "generated,test", "--tests", "tests/unit", "--json"))["result"]
    assert made["pipelines"] == [{"name": "quick", "steps": ["generated", "test"], "tests": ["tests/unit"]}]
    put = as_json(cli("pipeline", "on", "before-submit", "quick", "--json"))["result"]
    assert put["triggers"] == {"before-submit": ["quick"]}
    assert as_json(cli("pipeline", "on", "before-push", "quick", "--local", "--json"))["result"]["local"] == {
        "before-push": ["quick"]}
    shown = cli("pipeline", "list").stdout
    assert "quick：生成ファイル・テスト（流す試験：tests/unit）" in shown and "提出の前（before-submit）：quick" in shown
    assert "push の前（before-push）：quick（このPCだけ）" in shown
    assert as_json(cli("pipeline", "add", "lint", "--steps", "lint", "--json"))["error"]["code"] == "invalid_argument"
    assert as_json(cli("pipeline", "on", "before-lunch", "quick", "--json"))["error"]["code"] == "invalid_argument"
    assert as_json(cli("pipeline", "add", "gen", "--steps", "generated", "--json"))["ok"]
    assert as_json(cli("pipeline", "run", "gen", "--json"))["result"]["ok"]
    removed = as_json(cli("pipeline", "remove", "quick", "--json"))["result"]
    assert removed["triggers"] == {} and removed["local"] == {}   # このPCの当て方も、なくなったものは出さない


def test_workspace_names_stay_inside(module):
    """作業空間の名前は、外へ出るもの・パスの区切りを受け付けない。"""
    from ecobuild.errors import EcoBuildError
    assert module.workspace_place("12") == module.root / ".ecobuild" / "w" / "12"
    assert module.workspace_place("r5-x_1") == module.root / ".ecobuild" / "w" / "r5-x_1"
    for name in ("..", "a/b", "a\\b", "", ".hidden", "-x", "x" * 33):
        with pytest.raises(EcoBuildError):
            module.workspace_place(name)


def test_start_refuses_task_held_by_the_original(cli, module):
    """元の clone がそのタスクブランチを取り出していれば、分かる誤りにする（同じブランチは1か所だけ）。ほかのタスクは始められる。"""
    assert cli("task", "new", "その場").exit_code == 0
    assert cli("task", "new", "別").exit_code == 0
    module.repository.task(1).start(name="その場")       # 前の版のように、元の clone で取り出した
    refused = as_json(cli("task", "start", "1", "--json"))["error"]
    assert refused["code"] == "branch_checked_out" and "switch main" in refused["hint"]
    assert start(cli, "task", "start", "2", "--name", "別") == module.root / ".ecobuild" / "w" / "2"


@pytest.mark.parametrize("answer, said", [("", "--yes を付けて"), ("n\n", "中断しました")])
def test_confirmation_without_an_answer(module, monkeypatch, capsys, answer, said):
    """確認（[y/N]）に答えがない（標準入力が閉じている）なら、--yes を案内する誤り。「いいえ」なら中断。
    どちらも「予期しないエラー（Abort）」にしない。"""
    import io
    import sys
    from types import SimpleNamespace
    import ecobuild_cli
    from ecowork import Repository
    monkeypatch.setattr(_github, "default", lambda: module.repository.github)
    monkeypatch.chdir(module.root)
    monkeypatch.setattr(Repository, "prune_task_branches",
                        lambda self, dry_run=False: SimpleNamespace(removed=("task/9-x",)))

    class Terminal(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.setattr(sys, "stdin", Terminal(answer))
    with pytest.raises(SystemExit) as stopped:
        ecobuild_cli.main(["task", "prune"])
    error = capsys.readouterr().err
    assert stopped.value.code == 1 and said in error and "予期しない" not in error, error


def test_apply_partial_in_the_workspace_keeps_it(cli, module):
    """task apply --partial：作業空間の中で反映しても、タスクと作業空間は残り、作成元の最新から続ける。"""
    work = start(cli, "task", "new", "途中まで", "--start", "--name", "途中")
    write(work / "calc.cpp", "int calc;\n")
    assert cli("task", "commit", "--message", "途中まで").exit_code == 0
    applied = cli("task", "apply", "--partial")
    assert applied.exit_code == 0, applied.output
    assert "タスクは続きます" in applied.stdout and "作り直しました" in applied.stdout
    assert work.exists() and git(work, "branch", "--show-current") == "task/1-途中"
    assert git(work, "rev-parse", "HEAD") == git(module.root, "rev-parse", "origin/main")
    assert as_json(cli("status", "--json"))["result"]["task"] == 1
