"""タスクの完了（finish）・承認（approve）・差し戻し（reject）・取り下げ（withdraw）と、変更の記録（record）。

番号はすべてタスクの番号。PRはその実現の方法として内部で引く。
"""

from dataclasses import replace

import pytest

from helpers import git, write
from ecowork.errors import ErrorCode, WorkError
from ecowork.github import Check, PullRequestActivity, RunInfo

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def started(repository, title="t", **options):
    task = repository.create_task(title)
    return task, task.start(**options)


def recorded(task_branch, name="a.txt", text="a\n", message="a"):
    write(task_branch._repository.root / name, text)
    return task_branch.record(message)


def by_someone_else(repository, number):
    """提出の作成者を他人にする（GitHubは自分の提出を承認させない）。"""
    pr = repository.submission(number)
    repository.github.pulls[pr.number] = replace(repository.github.pulls[pr.number], author="someone")
    return pr


# 記録（task commit） ------------------------------------------------------------------

def test_record_includes_new_and_deleted_files(repository):
    _, task_branch = started(repository)
    write(repository.root / "new.txt", "n\n")
    (repository.root / "README.md").unlink()
    result = task_branch.record("足して消す")
    assert set(result.files) == {"new.txt", "README.md"} and result.skipped == ()
    assert repository.git.working_tree().clean


def test_record_skips_new_files_that_are_not_included(repository):
    _, task_branch = started(repository)
    write(repository.root / "keep.cpp", "k\n")
    write(repository.root / "junk.tmp", "j\n")
    result = task_branch.record("記録", include=lambda p: p.endswith(".cpp"))
    assert result.files == ("keep.cpp",) and result.skipped == ("junk.tmp",)
    assert repository.git.working_tree().untracked == ("junk.tmp",)
    # 何もなければ止め、含めなかったものを案内する
    with pytest.raises(WorkError) as error:
        task_branch.record("もう一度", include=lambda p: p.endswith(".cpp"))
    assert error.value.code == ErrorCode.NOTHING_TO_COMMIT and "junk.tmp" in error.value.hint


def test_record_only_given_paths(repository):
    _, task_branch = started(repository)
    write(repository.root / "a.txt", "a\n")
    write(repository.root / "b.txt", "b\n")
    result = task_branch.record("aだけ", ("a.txt",), include=lambda p: False)
    assert result.files == ("a.txt",)
    assert repository.git.working_tree().untracked == ("b.txt",)


def test_record_amend_keeps_message(repository):
    _, task_branch = started(repository)
    recorded(task_branch, message="最初")
    write(repository.root / "b.txt", "b\n")
    result = task_branch.record("", amend=True)
    assert result.message == "最初" and set(result.files) == {"a.txt", "b.txt"}


# 完了（task finish） ------------------------------------------------------------------

def test_finish_submits_merges_and_cleans_up(repository):
    """提出していなくても、提出してから取り込み、Issueを閉じ、手元とGitHubのタスクブランチを片付ける。"""
    task, task_branch = started(repository)
    recorded(task_branch)
    git(repository.root, "commit", "--quiet", "--allow-empty", "-m", "未push")   # 未pushのコミットも送る
    result = repository.finish()
    assert result.task == task.number and result.closed_issue == task.number and not result.partial
    assert result.removed and result.switched_to == "main"
    assert repository.git.current_branch() == "main" and (repository.root / "a.txt").exists()
    assert not repository.git.has_local_branch(task_branch.branch)
    assert not repository.git.has_remote_branch(task_branch.branch)
    assert repository.task(task.number).state == "closed"
    merged = repository.github.pulls[result.pull_request]
    assert merged.state == "merged"
    log = git(repository.root, "log", "-1", "--format=%s")
    assert log == f"t (#{result.pull_request})"


def test_finish_with_subject_and_from_elsewhere(repository):
    """番号を指定すればタスクブランチの外からも完了できる。件名は --subject。"""
    task, task_branch = started(repository)
    recorded(task_branch)
    task_branch.submit()
    repository.git.switch("main")
    result = repository.finish(task.number, subject="中身に合った件名")
    assert result.subject == "中身に合った件名" and result.switched_to is None and result.removed
    repository.git.merge("origin/main", ff_only=True)
    assert git(repository.root, "log", "-1", "--format=%s") == f"中身に合った件名 (#{result.pull_request})"


def test_finish_refuses_uncommitted_and_draft_and_nothing(repository):
    task, task_branch = started(repository)
    assert code_of(repository.finish) == ErrorCode.NOTHING_TO_SUBMIT
    write(repository.root / "README.md", "変更\n")
    assert code_of(repository.finish) == ErrorCode.DIRTY_WORKING_TREE
    task_branch.record("変更")
    task_branch.submit(draft=True)
    assert code_of(repository.finish) == ErrorCode.PULL_REQUEST_DRAFT
    task_branch.submit()                     # もう一度 submit で下書きを解除
    assert not repository.submission(task.number).draft
    assert repository.finish().closed_issue == task.number


def test_finish_waits_for_ci(repository):
    task, task_branch = started(repository)
    write(repository.root / ".github/workflows/ci.yml", "name: ci\n")
    recorded(task_branch)
    pr = task_branch.submit()
    sha = repository.github.get_pull_request(repository.root, pr.number).head_sha
    github = repository.github
    github.runs = [RunInfo(1, "build", task_branch.branch, "pull_request", "in_progress", "", "u", "t", sha)]
    ticks = []

    def sleep(seconds):
        ticks.append(seconds)
        github.runs = [replace(github.runs[0], status="completed", conclusion="failure")]

    with pytest.raises(WorkError) as error:
        repository.finish(sleep=sleep)
    assert error.value.code == ErrorCode.CHECKS_FAILED and ticks and "task finish" in error.value.hint
    assert repository.task(task.number).state == "open"
    github.runs = [replace(github.runs[0], conclusion="success")]
    github.activity[pr.number] = PullRequestActivity((), (), (Check("build", "completed", "success"),), "MERGEABLE")
    result = repository.finish(sleep=sleep)
    assert [r.conclusion for r in result.checks] == ["success"] and result.closed_issue == task.number


def test_finish_partial_rebuilds_and_keeps_going(repository):
    task, task_branch = started(repository)
    recorded(task_branch)
    task_branch.submit(partial=True)
    result = repository.finish()
    assert result.partial and result.branch_rebuilt and not result.removed and result.next is None
    assert repository.task(task.number).state == "open"
    assert repository.git.current_branch() == task_branch.branch


def test_finish_chooses_whether_to_close(repository):
    """完了で閉じるかを決める：中間提出も partial=False なら閉じる。partial=True なら最後の提出でも続ける。"""
    task, task_branch = started(repository)
    recorded(task_branch)
    task_branch.submit(partial=True)
    result = repository.finish(partial=False)
    assert not result.partial and result.closed_issue == task.number and result.removed
    assert repository.task(task.number).state == "closed"

    task, task_branch = started(repository, title="u")
    recorded(task_branch, name="b.txt")
    task_branch.submit()
    result = repository.finish(partial=True)
    assert result.partial and result.branch_rebuilt and repository.task(task.number).state == "open"


def test_finish_closes_after_partial_with_nothing_new(repository):
    """中間の取り込みの後、続きの変更がないまま完了：取り込むものなしで閉じて片付ける。"""
    task, task_branch = started(repository)
    recorded(task_branch)
    first = repository.finish(partial=True)
    assert first.partial and repository.task(task.number).state == "open"
    assert code_of(lambda: repository.finish(partial=True)) == ErrorCode.NOTHING_TO_SUBMIT
    result = repository.finish(task.number)
    assert not result.partial and result.pull_request == first.pull_request and result.closed_issue == task.number
    assert result.removed and result.switched_to == "main"
    assert repository.task(task.number).state == "closed"
    assert not repository.git.has_remote_branch(task_branch.branch)


def test_finish_resumes_after_a_failure(repository, monkeypatch):
    repository.create_branch("develop")    # main 以外へは GitHub が Issue を閉じない（ecowork が閉じる）
    task, task_branch = started(repository, base="develop")
    recorded(task_branch)
    github = repository.github

    def failing(*args, **kwargs):
        raise WorkError(ErrorCode.GITHUB_ERROR, "一時的な失敗")

    original = github.close_issue
    monkeypatch.setattr(github, "close_issue", failing)
    with pytest.raises(WorkError) as error:
        repository.finish()
    assert f"task finish {task.number}" in error.value.hint
    monkeypatch.setattr(github, "close_issue", original)
    result = repository.finish(task.number)
    assert result.resumed and result.closed_issue == task.number and result.removed
    assert code_of(lambda: repository.finish(task.number)) == ErrorCode.TASK_CLOSED


def test_finish_requires_approval_when_configured(repository):
    task, task_branch = started(repository)
    recorded(task_branch)
    task_branch.submit()
    repository.require_approval = True
    assert code_of(repository.finish) == ErrorCode.APPROVAL_REQUIRED
    by_someone_else(repository, task.number)
    result = repository.approve(task.number)
    assert result.approved and result.closed_issue == task.number


# 承認・差し戻し・取り下げ ------------------------------------------------------------

def test_review_then_approve_returns_and_finishes(repository):
    task, task_branch = started(repository)
    recorded(task_branch)
    task_branch.submit()
    repository.git.switch("main")
    by_someone_else(repository, task.number)
    review = repository.review_task(task.number)
    assert review.task == task.number and repository.status().reviewing_task == task.number
    result = repository.approve(task.number, "よいです")
    assert result.returned_to == "main" and result.approved and result.closed_issue == task.number
    assert repository.status().reviewing is None and repository.git.current_branch() == "main"
    assert not repository.git.has_local_branch(task_branch.branch)    # 作業者の手元（同じclone）も片付いた


def test_own_submission_cannot_be_approved(repository):
    task, task_branch = started(repository)
    recorded(task_branch)
    task_branch.submit()
    with pytest.raises(WorkError) as error:
        repository.approve(task.number)
    assert error.value.code == ErrorCode.OWN_PULL_REQUEST and f"task finish {task.number}" in error.value.hint


def test_reject_and_resubmit(repository):
    task, task_branch = started(repository)
    recorded(task_branch)
    task_branch.submit()
    by_someone_else(repository, task.number)
    assert code_of(lambda: repository.reject(task.number, " ")) == ErrorCode.INVALID_ARGUMENT
    result = repository.reject(task.number, "名前を直して")
    assert result.task == task.number and result.returned_to is None
    reviews = repository.github.pull_request_activity(repository.root, result.pull_request).reviews
    assert reviews[-1].state == "CHANGES_REQUESTED"


def test_withdraw_then_submit_again(repository):
    task, task_branch = started(repository)
    recorded(task_branch)
    first = task_branch.submit()
    repository.withdraw()
    assert repository.submission(task.number) is None
    assert repository.github.pulls[first.number].state == "closed"
    second = task_branch.submit()
    assert second.number != first.number and repository.submission(task.number).number == second.number


# 片付け・取り消し・差分 ---------------------------------------------------------------

def test_finished_workspaces_are_tidied_on_next_start(repository, tmp_path):
    """別の場所で完了したタスクの手元のタスクブランチは、次の task start で片付く。"""
    task, task_branch = started(repository)
    recorded(task_branch)
    task_branch.submit()
    repository.git.switch("main")
    repository.github.merge_pull_request(repository.root, repository.submission(task.number).number,
                                         squash=True, subject="別の場所で")
    git(repository.root, "push", "--quiet", "origin", "--delete", task_branch.branch)
    other = repository.create_task("次")
    repository.git.fetch()
    other.start()
    assert not repository.git.has_local_branch(task_branch.branch)
    assert any(task_branch.branch in n for n in repository.notices)


def test_clean_one_workspace(repository):
    task, task_branch = started(repository)
    recorded(task_branch)
    task_branch.push()
    result = repository.prune_task_branch(task.number)      # 開いているタスク：手元の写しだけを消す
    assert result.remote and result.switched_to == "main"
    assert not repository.git.has_local_branch(task_branch.branch) and repository.git.has_remote_branch(task_branch.branch)


def test_clean_dry_run_matches_the_real_run(repository):
    """今いるタスクブランチに未コミットの変更があれば、dry-run でも「残す」に数える。"""
    task, task_branch = started(repository)
    recorded(task_branch)
    task_branch.submit()
    repository.github.merge_pull_request(repository.root, repository.submission(task.number).number,
                                         squash=True, subject="s")
    write(repository.root / "a.txt", "変更\n")
    preview = repository.prune_task_branches(dry_run=True)
    assert preview.removed == () and preview.skipped[0].branch == task_branch.branch


def test_revert_task_and_diff(repository):
    task, task_branch = started(repository)
    recorded(task_branch)
    task_branch.submit()
    assert "+a" in repository.task_diff(task.number)
    repository.finish()
    reverted = repository.revert_task(task.number)
    assert reverted.reverted_task == task.number and repository.git.current_branch() == reverted.branch
    assert not (repository.root / "a.txt").exists()
    assert code_of(lambda: repository.revert_task(reverted.task)) == ErrorCode.PULL_REQUEST_NOT_OPEN


def test_tasks_show_submissions(repository):
    task, task_branch = started(repository)
    recorded(task_branch)
    task_branch.submit(draft=True)
    listed = {t.number: t for t in repository.tasks()}
    assert listed[task.number].submission.draft and listed[task.number].submission.base == "main"   # 取り込み先も
    assert [t.number for t in repository.tasks(submitted=True)] == [task.number]


def test_merge_branch_by_name(repository):
    repository.create_branch("develop")
    task, task_branch = started(repository, base="develop")
    recorded(task_branch)
    repository.finish()
    repository.branch("develop").submit(into="main")
    assert repository.merge_branch("develop").method == "merge"
    assert code_of(lambda: repository.merge_branch("develop")) == ErrorCode.NO_PULL_REQUEST


def test_new_files_outside_the_work_do_not_block(repository):
    """include_new に当たらない新しいファイル（メモ等）は、タスクブランチの切り替え・やめる等を止めない。"""
    repository.include_new = lambda p: p.endswith(".cpp")
    task, task_branch = started(repository)
    write(repository.root / "notes.tmp", "メモ\n")
    other = repository.create_task("次").start()          # 止まらない
    assert other.number != task.number and (repository.root / "notes.tmp").exists()
    write(repository.root / "new.cpp", "x\n")
    assert code_of(lambda: repository.task(task.number).start()) == ErrorCode.DIRTY_WORKING_TREE
