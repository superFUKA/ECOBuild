"""タスク管理（ラベル・担当者・コメント・絞り込み）と、CIの完了を待つ操作。"""

import pytest

from helpers import write
from ecowork.errors import ErrorCode, WorkError
from ecowork.github import RunInfo

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def test_labels_assignees_and_filters(repository):
    github = repository.github
    bug = repository.create_task("落ちる", body="0で割ると落ちる", labels=("bug",), assignees=("someone",))
    docs = repository.create_task("説明を書く", labels=("docs",))
    assert (bug.labels, bug.assignees) == (("bug",), ("someone",))

    assert [t.number for t in repository.tasks(label="bug")] == [bug.number]
    assert [t.number for t in repository.tasks(assignee="someone")] == [bug.number]
    assert [t.number for t in repository.tasks(search="0で割る")] == [bug.number]
    assert repository.tasks(label="docs")[0].labels == ("docs",)

    edited = repository.edit_task(docs.number, add_labels=("good first issue",), remove_labels=("docs",),
                                  add_assignees=("@me",))
    assert edited.labels == ("good first issue",) and edited.assignees == (github.owner,)
    assert [t.number for t in repository.tasks(assignee="@me")] == [docs.number]
    edited = repository.edit_task(docs.number, remove_assignees=("@me",))
    assert edited.assignees == ()
    assert code_of(lambda: repository.edit_task(docs.number)) == ErrorCode.INVALID_ARGUMENT


def test_start_claims_unassigned_task_only(repository):
    github = repository.github
    mine = repository.create_task("自分の作業")
    repository.git.run("switch", "--quiet", "main")
    workspace = mine.start()
    assert github.issues[mine.number].assignees == (github.owner,)  # 誰が作業しているかGitHubで分かる
    repository.git.run("switch", "--quiet", "main")
    theirs = repository.create_task("割り当て済み", assignees=("someone",))
    theirs.start()
    assert github.issues[theirs.number].assignees == ("someone",)  # 既にいる担当者は変えない
    assert workspace.number == mine.number


def test_returning_to_workspace_claims_unassigned_task(repository):
    github = repository.github
    task = repository.create_task("戻る作業")
    repository.git.run("switch", "--quiet", "main")
    task.start()
    repository.edit_task(task.number, remove_assignees=("@me",))
    repository.git.run("switch", "--quiet", "main")
    repository.task(task.number).start()                             # 手元にある作業空間へ戻る
    assert github.issues[task.number].assignees == (github.owner,)


def test_comments_are_kept_on_the_issue(repository):
    task = repository.create_task("申し送り")
    task.start()
    repository.comment_task(None, "途中まで：計算は済み、表示が残り")  # 今いる作業空間のタスク
    repository.comment_task(task.number, "表示も済み")
    status = repository.task_status()
    assert [c.body for c in status.comments] == ["途中まで：計算は済み、表示が残り", "表示も済み"]
    assert code_of(lambda: repository.comment_task(task.number, "  ")) == ErrorCode.INVALID_ARGUMENT


def _run(id, sha, status="completed", conclusion="success", branch="task/1"):
    return RunInfo(id, "build", branch, "push", status, conclusion, f"u{id}", "", sha)


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = 0

    def sleep(self, seconds):
        self.now += seconds
        self.sleeps += 1

    def __call__(self):
        return self.now


def test_ci_wait_until_runs_of_pushed_commit_finish(repository):
    github = repository.github
    workspace = repository.create_task("CIを待つ").start()
    sha = repository.git.rev_parse("origin/task/1")
    clock = Clock()
    github.runs = [_run(1, "old", conclusion="failure")]  # 前のコミットの実行は見ない

    def appear(seconds):
        clock.sleep(seconds)
        if clock.sleeps == 2:
            github.runs = [_run(2, sha, status="in_progress", conclusion="")] + github.runs
        if clock.sleeps == 4:
            github.runs = [_run(2, sha)] + github.runs[1:]

    runs = repository.ci_wait(interval=10, sleep=appear, clock=clock)
    assert [r.id for r in runs] == [2] and clock.sleeps == 4

    write(repository.root / "a.txt", "a\n")
    workspace.stage("a.txt")
    workspace.commit("失敗する")
    workspace.push()
    new_sha = repository.git.rev_parse("origin/task/1")
    github.runs = [_run(3, new_sha, conclusion="failure")]
    with pytest.raises(WorkError) as error:
        repository.ci_wait(sleep=clock.sleep, clock=clock)
    assert error.value.code == ErrorCode.CHECKS_FAILED and "ecobuild ci logs" in error.value.hint

    github.runs = [_run(4, new_sha, status="queued", conclusion="")]
    assert code_of(lambda: repository.ci_wait(timeout=60, interval=10, sleep=clock.sleep,
                                              clock=clock)) == ErrorCode.CHECKS_PENDING
    github.runs = []
    assert code_of(lambda: repository.ci_wait(start_grace=30, interval=10, sleep=clock.sleep,
                                              clock=clock)) == ErrorCode.NO_CI_RUN


def test_ci_wait_for_pull_request_and_secret_removal(repository):
    github = repository.github
    workspace = repository.create_task("PRのCI").start()
    write(repository.root / "a.txt", "a\n")
    workspace.stage("a.txt")
    workspace.commit("変更")
    pr = workspace.submit()
    github.runs = [_run(5, github.get_pull_request(None, pr.number).head_sha)]
    repository.git.run("switch", "--quiet", "main")
    assert [r.id for r in repository.ci_wait(pr.number)] == [5]

    repository.set_secret("TOKEN", "x")
    assert repository.delete_secret("TOKEN") == "TOKEN" and repository.secrets() == []
    assert code_of(lambda: repository.delete_secret("TOKEN")) == ErrorCode.INVALID_ARGUMENT
