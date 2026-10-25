"""タスクの管理・PRの確認・履歴・取り消し等（範囲外の機能）。偽のGitHub＋手元のbareで確かめる。"""

import pytest

from helpers import git, write
from ecowork import Repository
from ecowork.errors import ErrorCode, WorkError
from ecowork.git import same_path
from ecowork.github import Check, Comment, PullRequestActivity, Review

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def commit_file(task_branch, root, name, text, message):
    write(root / name, text)
    task_branch.stage(name)
    return task_branch.commit(message)


def finish(repository, task_branch, name, text, message):
    commit_file(task_branch, repository.root, name, text, message)
    pr = task_branch.submit()
    repository.pull_request().merge()
    repository.prune_task_branches()
    return pr


def test_task_management(repository):
    first = repository.create_task("一つ目", body="本文")
    second = repository.create_task("二つ目")
    second.start()
    listed = repository.tasks()
    assert [(t.number, t.task_branch, t.current) for t in listed] == [(1, False, False), (2, True, True)]
    assert repository.edit_task(1, title="一つ目（改）").title == "一つ目（改）"
    assert code_of(lambda: repository.edit_task(1)) == ErrorCode.INVALID_ARGUMENT
    assert repository.close_task(first.number).state == "closed"
    assert code_of(lambda: repository.close_task(first.number)) == ErrorCode.TASK_CLOSED
    assert [t.number for t in repository.tasks()] == [2]
    assert [t.number for t in repository.tasks(closed=True)] == [1, 2]
    assert repository.reopen_task(first.number).state == "open"
    assert code_of(lambda: repository.reopen_task(first.number)) == ErrorCode.INVALID_ARGUMENT


def test_task_status_shows_reviews_and_checks(repository):
    task_branch = repository.create_task("t", body="やること").start()
    status = repository.task_status()
    assert (status.number, status.body, status.task_branch, status.base, status.pull_request) == (1, "やること", True,
                                                                                              "main", None)
    commit_file(task_branch, repository.root, "a.txt", "a\n", "a")
    pr = task_branch.submit()
    repository.github.activity[pr.number] = PullRequestActivity(
        (Review("alice", "CHANGES_REQUESTED", "直して"),), (Comment("bob", "了解"),),
        (Check("build", "completed", "failure"),), "MERGEABLE")
    status = repository.task_status(1)
    assert status.pull_request.number == pr.number
    assert [c.split(" ", 1)[1] for c in status.commits] == ["a"]     # 提出に入るコミット（作成元にないもの）
    assert status.activity.reviews[0].state == "CHANGES_REQUESTED" and status.activity.checks[0].conclusion == "failure"


@pytest.mark.needs_git_2_48
def test_review_pull_request_in_a_review_workspace(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    other_root = tmp_path / "other"
    git(tmp_path, "clone", "--quiet", str(remote), str(other_root))
    other = Repository(other_root, github=repository.github, command="ecobuild")
    theirs = other.create_task("他人の作業").start()
    commit_file(theirs, other_root, "theirs.txt", "theirs\n", "他人の変更")
    pr = theirs.submit()

    write(repository.root / "dirty.txt", "x\n")      # 元の clone の変更は、確認の邪魔にならない（触らない）
    result = repository.review_in(pr.number, tmp_path / "r")
    assert result.head == "task/1" and same_path(result.workspace, tmp_path / "r")
    assert (tmp_path / "r" / "theirs.txt").exists() and not (repository.root / "theirs.txt").exists()
    assert repository.git.current_branch() == "main" and repository.status().reviewing is None
    reviewer = Repository(result.workspace, github=repository.github, command="ecobuild")
    status = reviewer.status()
    assert status.reviewing == pr.number and status.task is None
    assert reviewer.current_task_branch() is None  # コミットはできない（タスクブランチでない）
    assert same_path(repository.review_in(pr.number, tmp_path / "r2").workspace, tmp_path / "r")   # 既にあればそこ

    write(tmp_path / "r" / "README.md", "変えた\n")
    assert code_of(reviewer.end_review) == ErrorCode.DIRTY_WORKING_TREE
    git(tmp_path / "r", "checkout", "--", "README.md")
    back = reviewer.end_review()
    assert same_path(back.workspace, tmp_path / "r") and not (tmp_path / "r").exists()
    assert same_path(reviewer.root, repository.root)      # 消した場所から、元の clone へ移る
    assert reviewer.status().reviewing is None
    assert code_of(repository.end_review) == ErrorCode.INVALID_ARGUMENT

    repository.review_in(pr.number, tmp_path / "r3")
    assert repository.end_review(pr.number).task == 1 and not (tmp_path / "r3").exists()   # 外から番号で終える


def test_log_revert_ignore_release(repository):
    root = repository.root
    pr = finish(repository, repository.create_task("機能A").start(), "a.txt", "a\n", "機能Aを追加")
    entries = repository.log(count=5)
    assert entries[0].subject == f"機能A (#{pr.number})" and entries[0].pull_request == pr.number
    assert entries[0].issue == 1
    assert "a.txt" in repository.show()
    parent, sha = repository.show_revisions()
    assert sha == repository.git.rev_parse("HEAD") and "a.txt" in repository.git.output("diff", "--stat", parent, sha)
    assert len(repository.blame("a.txt").splitlines()) == 1

    reverted = repository.revert(pr.number)
    assert repository.current_task_branch().branch == reverted.branch and not (root / "a.txt").exists()
    assert repository.task(reverted.task).title == "「機能A」を取り消す"
    assert repository.diff(base=True).count("a.txt") >= 1
    repository.current_task_branch().submit()
    repository.pull_request().merge()
    repository.prune_task_branches()
    assert code_of(lambda: repository.revert(99)) == ErrorCode.NO_PULL_REQUEST

    assert code_of(lambda: repository.ignore("*.log")) == ErrorCode.NOT_ON_TASK_BRANCH  # main では変えない
    task_branch = repository.create_task("除外").start()
    assert repository.ignore("*.log", "out/", "*.log") == ("*.log", "out/")
    assert repository.ignore("*.log") == ()
    assert (root / ".gitignore").read_text(encoding="utf-8").splitlines()[-2:] == ["*.log", "out/"]
    finish(repository, task_branch, "b.txt", "b\n", "除外")

    release = repository.create_release("v1.0.0", title="最初", notes="")
    assert release.tag == "v1.0.0" and [r.tag for r in repository.releases()] == ["v1.0.0"]
    assert code_of(lambda: repository.create_release("v1.0.0")) == ErrorCode.ALREADY_EXISTS
    assert code_of(lambda: repository.create_release("v2", target="task/9")) == ErrorCode.INVALID_BASE


def test_log_of_the_submission_and_of_what_push_sends(repository):
    """log --not-in：作成元にないコミット（提出に入るもの、未Pushも）。--unpushed：Push で送るもの（push と同じ）。"""
    root = repository.root
    task_branch = repository.create_task("ログ").start()
    commit_file(task_branch, root, "a.txt", "a\n", "送った")
    task_branch.push()
    commit_file(task_branch, root, "b.txt", "b\n", "まだ")
    base = task_branch.base
    assert [e.subject for e in repository.log(not_in=base)] == ["まだ", "送った"]
    assert [e.subject for e in repository.log(unpushed=True)] == ["まだ"]
    assert [c.split(" ", 1)[1] for c in task_branch.push(dry_run=True).commits] == ["まだ"]
    assert code_of(lambda: repository.log(not_in="nope")) == ErrorCode.REVISION_NOT_FOUND
    # --branch：取り出していないブランチの履歴（取り出しているタスクブランチのコミットは入らない）
    assert "まだ" not in [e.subject for e in repository.log(branch=base)]
    assert [e.subject for e in repository.log(branch=task_branch.branch, not_in=base)] == ["送った"]   # GitHub のもの
    assert code_of(lambda: repository.log(branch="nope")) == ErrorCode.REVISION_NOT_FOUND
    assert code_of(lambda: repository.log(branch=base, unpushed=True)) == ErrorCode.INVALID_ARGUMENT


def test_close_and_clean_keep_unfinished_work(repository):
    """Issueを閉じるだけでは、マージしていない作業は消えない（作業の終わり方は merge か drop）。"""
    root = repository.root
    task_branch = repository.create_task("途中").start()
    commit_file(task_branch, root, "a.txt", "a\n", "途中の変更")
    task_branch.push()
    with pytest.raises(WorkError) as error:
        repository.close_task(1)
    assert error.value.code == ErrorCode.UNFINISHED_WORK and "task drop" in error.value.hint
    pr = task_branch.submit()
    assert code_of(lambda: repository.close_task(1)) == ErrorCode.UNFINISHED_WORK  # 開いているPR
    # GitHubで直接閉じられても、task prune はマージしていないタスクブランチを残す
    repository.github.close_issue(root, 1)
    result = repository.prune_task_branches()
    assert result.removed == () and "マージしていないコミット" in result.skipped[0].reason
    assert repository.github.pulls[pr.number].state == "open"
    # タスクブランチのないIssue・作業の終わったIssueは閉じられる
    repository.create_task("作業なし")
    assert repository.close_task(3).state == "closed"


def test_stash_pop_stays_in_its_workspace(repository):
    """別のタスクブランチで退避した変更は戻さない。main で退避した変更はタスクブランチへ持ち込める。"""
    root = repository.root
    write(root / "main.txt", "main\n")
    repository.stash()
    first = repository.create_task("一つ目").start()
    repository.stash_pop()  # main で始めてしまった変更を、タスクブランチへ持ち込む
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


@pytest.mark.needs_git_2_48
def test_status_fetch_and_workspace(repository, remote_and_clone, tmp_path):
    task = repository.create_task("並行作業")
    dedicated = repository.start_task_in(task.number, tmp_path / "1").repository
    assert dedicated.current_task_branch().number == task.number
    assert repository.current_task_branch() is None  # 元のcloneはそのまま
    write(tmp_path / "2" / "x.txt", "x\n")
    assert code_of(lambda: repository.start_task_in(repository.create_task("b").number, tmp_path / "2")) \
        == ErrorCode.ALREADY_EXISTS

    finish(repository, repository.create_task("先に入る").start(), "b.txt", "b\n", "b")
    assert dedicated.status().base_behind is None
    assert dedicated.status(fetch=True).base_behind == 1


@pytest.mark.needs_git_2_48
def test_a_workspace_that_cannot_be_opened_is_removed(repository, tmp_path):
    """作業空間を作った後に開けなければ、作りかけを残さない（同じ場所でやり直せるように）。"""
    def refuse(root):
        raise WorkError(ErrorCode.GIT_ERROR, "開けません")
    task = repository.create_task("a")
    assert code_of(lambda: repository.start_task_in(task.number, tmp_path / "ws", open=refuse)) == ErrorCode.GIT_ERROR
    assert not (tmp_path / "ws").exists() and len(repository.git.worktrees()) == 1
    assert repository.start_task_in(task.number, tmp_path / "ws").created


def test_merge_stops_when_checks_failed(repository):
    """CIが失敗したPRはマージしない（--ignore-checks で続ける）。仮運用3回目で追加。"""
    task_branch = repository.create_task("t").start()
    commit_file(task_branch, repository.root, "a.txt", "a\n", "a")
    pr = task_branch.submit()
    repository.github.activity[pr.number] = PullRequestActivity((), (), (Check("build", "completed", "failure"),),
                                                                "MERGEABLE")
    with pytest.raises(WorkError) as error:
        repository.pull_request().merge()
    assert error.value.code == ErrorCode.CHECKS_FAILED and "--ignore-checks" in error.value.hint
    # 実行中（ci rerun の直後等）も待つ。仮運用で、再実行中に失敗する変更がマージされた
    repository.github.activity[pr.number] = PullRequestActivity((), (), (Check("build", "in_progress", ""),),
                                                                "MERGEABLE")
    assert code_of(lambda: repository.pull_request().merge()) == ErrorCode.CHECKS_PENDING
    # ワークフローがあるのに結果がまだない（PRを出した直後）も待つ
    repository.github.activity[pr.number] = PullRequestActivity((), (), (), "MERGEABLE")
    write(repository.root / ".github/workflows/ecobuild.yml", "name: build\n")
    assert code_of(lambda: repository.pull_request().merge()) == ErrorCode.CHECKS_PENDING
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
    assert [r.id for r in repository.ci_runs(branch="task/9")] == [3]
    assert [r.id for r in repository.ci_runs(all_branches=True)] == [2, 1, 3]
    assert repository.ci_failed_log() == (2, "run 2: error")
    assert repository.ci_rerun(failed_only=True) == 2 and github.reruns == [(2, True)]
    assert repository.ci_dispatch("ecobuild.yml") == "main" and github.dispatched == [("ecobuild.yml", "main")]
    assert code_of(lambda: repository.ci_dispatch("ecobuild.yml", "task/9")) == ErrorCode.BRANCH_NOT_FOUND
    repository.create_task("GitHubにない").start()
    git(repository.root, "push", "--quiet", "origin", "--delete", "task/1")
    assert code_of(lambda: repository.ci_dispatch("ecobuild.yml")) == ErrorCode.BRANCH_NOT_FOUND
    assert repository.set_secret("ECOBUILD_DEPS_TOKEN", "secret") == "ECOBUILD_DEPS_TOKEN"
    assert repository.secrets() == ["ECOBUILD_DEPS_TOKEN"]
    assert code_of(lambda: repository.set_secret("X", "")) == ErrorCode.INVALID_ARGUMENT
