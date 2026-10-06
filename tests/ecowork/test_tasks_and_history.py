"""タスクの管理・PRの確認・履歴・取り消し等（範囲外の機能）。偽のGitHub＋手元のbareで確かめる。"""

import pytest

from helpers import git, write
from ecowork import Repository
from ecowork.errors import ErrorCode, WorkError
from ecowork.github import Check, Comment, PullRequestActivity, Review

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def commit_file(workspace, root, name, text, message):
    write(root / name, text)
    workspace.stage(name)
    return workspace.commit(message)


def finish(repository, workspace, name, text, message):
    commit_file(workspace, repository.root, name, text, message)
    pr = workspace.submit()
    repository.pull_request().merge()
    repository.clean_workspaces()
    return pr


def test_task_management(repository):
    first = repository.create_task("一つ目", body="本文")
    second = repository.create_task("二つ目")
    second.start()
    listed = repository.tasks()
    assert [(t.number, t.workspace, t.current) for t in listed] == [(1, False, False), (2, True, True)]
    assert repository.edit_task(1, title="一つ目（改）").title == "一つ目（改）"
    assert code_of(lambda: repository.edit_task(1)) == ErrorCode.INVALID_ARGUMENT
    assert repository.close_task(first.number).state == "closed"
    assert code_of(lambda: repository.close_task(first.number)) == ErrorCode.TASK_CLOSED
    assert [t.number for t in repository.tasks()] == [2]
    assert [t.number for t in repository.tasks(closed=True)] == [1, 2]
    assert repository.reopen_task(first.number).state == "open"
    assert code_of(lambda: repository.reopen_task(first.number)) == ErrorCode.INVALID_ARGUMENT


def test_task_status_shows_reviews_and_checks(repository):
    workspace = repository.create_task("t", body="やること").start()
    status = repository.task_status()
    assert (status.number, status.body, status.workspace, status.base, status.pull_request) == (1, "やること", True,
                                                                                              "main", None)
    commit_file(workspace, repository.root, "a.txt", "a\n", "a")
    pr = workspace.submit()
    repository.github.activity[pr.number] = PullRequestActivity(
        (Review("alice", "CHANGES_REQUESTED", "直して"),), (Comment("bob", "了解"),),
        (Check("build", "completed", "failure"),), "MERGEABLE")
    status = repository.task_status(1)
    assert status.pull_request.number == pr.number
    assert status.activity.reviews[0].state == "CHANGES_REQUESTED" and status.activity.checks[0].conclusion == "failure"


def test_review_pull_request(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    other_root = tmp_path / "other"
    git(tmp_path, "clone", "--quiet", str(remote), str(other_root))
    other = Repository(other_root, github=repository.github, command="ecobuild")
    theirs = other.create_task("他人の作業").start()
    commit_file(theirs, other_root, "theirs.txt", "theirs\n", "他人の変更")
    pr = theirs.submit()

    write(repository.root / "dirty.txt", "x\n")
    assert code_of(lambda: repository.review(pr.number)) == ErrorCode.DIRTY_WORKING_TREE
    (repository.root / "dirty.txt").unlink()
    result = repository.review(pr.number)
    assert result.head == "task/1" and (repository.root / "theirs.txt").exists()
    status = repository.status()
    assert status.reviewing == pr.number and status.workspace is None
    assert repository.current_workspace() is None  # コミットはできない（作業空間でない）
    back = repository.end_review()
    assert back.returned_to == "main" and not (repository.root / "theirs.txt").exists()
    assert repository.status().reviewing is None
    assert code_of(repository.end_review) == ErrorCode.INVALID_ARGUMENT


def test_log_revert_ignore_release(repository):
    root = repository.root
    pr = finish(repository, repository.create_task("機能A").start(), "a.txt", "a\n", "機能Aを追加")
    entries = repository.log(count=5)
    assert entries[0].subject == f"機能A (#{pr.number})" and entries[0].pull_request == pr.number
    assert entries[0].issue == 1
    assert "a.txt" in repository.show()
    assert len(repository.blame("a.txt").splitlines()) == 1

    reverted = repository.revert(pr.number)
    assert repository.current_workspace().branch == reverted.branch and not (root / "a.txt").exists()
    assert repository.task(reverted.task).title == "「機能A」を取り消す"
    assert repository.diff(base=True).count("a.txt") >= 1
    repository.current_workspace().submit()
    repository.pull_request().merge()
    repository.clean_workspaces()
    assert code_of(lambda: repository.revert(99)) == ErrorCode.NO_PULL_REQUEST

    assert code_of(lambda: repository.ignore("*.log")) == ErrorCode.NOT_IN_WORKSPACE  # main では変えない
    workspace = repository.create_task("除外").start()
    assert repository.ignore("*.log", "out/", "*.log") == ("*.log", "out/")
    assert repository.ignore("*.log") == ()
    assert (root / ".gitignore").read_text(encoding="utf-8").splitlines()[-2:] == ["*.log", "out/"]
    finish(repository, workspace, "b.txt", "b\n", "除外")

    release = repository.create_release("v1.0.0", title="最初", notes="")
    assert release.tag == "v1.0.0" and [r.tag for r in repository.releases()] == ["v1.0.0"]
    assert code_of(lambda: repository.create_release("v1.0.0")) == ErrorCode.ALREADY_EXISTS
    assert code_of(lambda: repository.create_release("v2", target="task/9")) == ErrorCode.INVALID_BASE


def test_close_and_clean_keep_unfinished_work(repository):
    """Issueを閉じるだけでは、マージしていない作業は消えない（作業の終わり方は merge か drop）。"""
    root = repository.root
    workspace = repository.create_task("途中").start()
    commit_file(workspace, root, "a.txt", "a\n", "途中の変更")
    workspace.push()
    with pytest.raises(WorkError) as error:
        repository.close_task(1)
    assert error.value.code == ErrorCode.UNFINISHED_WORK and "task drop" in error.value.hint
    pr = workspace.submit()
    assert code_of(lambda: repository.close_task(1)) == ErrorCode.UNFINISHED_WORK  # 開いているPR
    # GitHubで直接閉じられても、task clean はマージしていない作業空間を残す
    repository.github.close_issue(root, 1)
    result = repository.clean_workspaces()
    assert result.removed == () and "マージしていないコミット" in result.skipped[0].reason
    assert repository.github.pulls[pr.number].state == "open"
    # 作業空間のないIssue・作業の終わったIssueは閉じられる
    repository.create_task("作業なし")
    assert repository.close_task(3).state == "closed"


def test_stash_pop_stays_in_its_workspace(repository):
    """別の作業空間で退避した変更は戻さない。main で退避した変更は作業空間へ持ち込める。"""
    root = repository.root
    write(root / "main.txt", "main\n")
    repository.stash()
    first = repository.create_task("一つ目").start()
    repository.stash_pop()  # main で始めてしまった変更を、作業空間へ持ち込む
    assert (root / "main.txt").exists()
    first.stage(all=True)
    first.commit("持ち込んだ変更")
    write(root / "first.txt", "first\n")
    repository.stash()
    repository.create_task("二つ目").start()
    with pytest.raises(WorkError) as error:
        repository.stash_pop()
    assert error.value.code == ErrorCode.UNFINISHED_WORK and "ecobuild task start 1" in error.value.hint
    repository.task(1).start()
    repository.stash_pop()
    assert (root / "first.txt").exists()


def test_status_fetch_and_dedicated_clone(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    task = repository.create_task("並行作業")
    dedicated = repository.clone_workspace(task.number, tmp_path / "Calc-1")
    assert dedicated.current_workspace().number == task.number
    assert repository.current_workspace() is None  # 元のcloneはそのまま
    assert code_of(lambda: repository.clone_workspace(task.number, tmp_path / "Calc-1")) == ErrorCode.ALREADY_EXISTS

    finish(repository, repository.create_task("先に入る").start(), "b.txt", "b\n", "b")
    assert dedicated.status().base_behind is None
    assert dedicated.status(fetch=True).base_behind == 1


def test_merge_stops_when_checks_failed(repository):
    """CIが失敗したPRはマージしない（--ignore-checks で続ける）。仮運用3回目で追加。"""
    workspace = repository.create_task("t").start()
    commit_file(workspace, repository.root, "a.txt", "a\n", "a")
    pr = workspace.submit()
    repository.github.activity[pr.number] = PullRequestActivity((), (), (Check("build", "completed", "failure"),),
                                                                "MERGEABLE")
    with pytest.raises(WorkError) as error:
        repository.pull_request().merge()
    assert error.value.code == ErrorCode.CHECKS_FAILED and "--ignore-checks" in error.value.hint
    assert repository.pull_request().merge(ignore_checks=True).closed_issue == 1


def test_ci_operations(repository):
    """CI（GitHub Actions）の実行・ログ・再実行・手動実行・シークレット。"""
    from ecowork.github import RunInfo
    github = repository.github
    assert code_of(lambda: repository.ci_failed_log()) == ErrorCode.NO_CI_RUN
    assert code_of(lambda: repository.ci_rerun()) == ErrorCode.NO_CI_RUN
    github.runs = [RunInfo(2, "build", "main", "push", "completed", "failure", "u2", "2026-10-06T12:00:00Z"),
                   RunInfo(1, "build", "main", "push", "completed", "success", "u1", "2026-10-06T11:00:00Z"),
                   RunInfo(3, "build", "task/9", "pull_request", "completed", "failure", "u3", "")]
    assert [r.id for r in repository.ci_runs()] == [2, 1]  # 今いるブランチ（main）だけ
    assert repository.ci_failed_log() == (2, "run 2: error")
    assert repository.ci_rerun(failed_only=True) == 2 and github.reruns == [(2, True)]
    assert repository.ci_dispatch("ecobuild.yml") == "main" and github.dispatched == [("ecobuild.yml", "main")]
    repository.create_task("未push").start()
    assert code_of(lambda: repository.ci_dispatch("ecobuild.yml")) == ErrorCode.BRANCH_NOT_FOUND
    assert repository.set_secret("ECOBUILD_DEPS_TOKEN", "secret") == "ECOBUILD_DEPS_TOKEN"
    assert repository.secrets() == ["ECOBUILD_DEPS_TOKEN"]
    assert code_of(lambda: repository.set_secret("X", "")) == ErrorCode.INVALID_ARGUMENT
