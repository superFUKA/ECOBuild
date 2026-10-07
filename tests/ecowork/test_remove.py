"""手元の作業空間だけを消す（task remove）。作業空間の本体はGitHubにあり、手元はその写し。"""

import pytest

from helpers import git, write
from ecowork import Repository
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def commit_file(workspace, root, name, text, message):
    write(root / name, text)
    workspace.stage(name)
    return workspace.commit(message)


def test_remove_and_resume_from_pushed_commits_with_same_base(repository):
    root, github = repository.root, repository.github
    repository.create_branch("develop")
    workspace = repository.create_task("消して再開する").start(base="develop")
    assert "<!-- ecowork-base: develop -->" in github.issues[1].body  # 作成元はGitHubにも残す
    commit_file(workspace, root, "a.txt", "a\n", "pushした変更")
    workspace.push()

    result = repository.remove_workspace()
    assert (result.branch, result.base, result.remote, result.switched_to) == ("task/1", "develop", True, "develop")
    assert git(root, "branch", "--show-current") == "develop"
    assert not repository.git.has_local_branch("task/1") and repository.git.has_remote_branch("task/1")
    assert repository.git.get_config("branch.task/1.ecowork-base") is None
    listed = {t.number: t for t in repository.tasks()}
    assert not listed[1].workspace and listed[1].remote
    status = repository.task_status(1)
    assert status.remote and not status.workspace and status.base == "develop"
    assert "ecowork-base" not in status.body  # 印は表示しない

    again = repository.task(1).start()  # --base なしでも、記録した作成元で
    assert (again.branch, again.base) == ("task/1", "develop")
    assert (root / "a.txt").read_text(encoding="utf-8") == "a\n"


def test_remove_refuses_what_github_does_not_have(repository):
    root = repository.root
    workspace = repository.create_task("未pushの作業").start()
    write(root / "a.txt", "a\n")
    assert code_of(repository.remove_workspace) == ErrorCode.DIRTY_WORKING_TREE
    workspace.stage("a.txt")
    workspace.commit("未push")
    with pytest.raises(WorkError) as error:
        repository.remove_workspace()
    assert error.value.code == ErrorCode.COMMITS_WOULD_BE_LOST and error.value.details == ["未push"]
    workspace.push()
    commit_file(workspace, root, "b.txt", "b\n", "pushの後のコミット")
    with pytest.raises(WorkError) as error:
        repository.remove_workspace(1)
    assert error.value.details == ["pushの後のコミット"]
    workspace.push()
    assert repository.remove_workspace(1).remote


def test_start_puts_new_workspace_on_github(repository):
    workspace = repository.create_task("すぐGitHubへ").start()
    assert repository.git.has_remote_branch(workspace.branch)
    assert repository.git.rev_parse("origin/task/1") == repository.git.rev_parse("origin/main")
    assert repository.git.output("rev-parse", "--abbrev-ref", "task/1@{upstream}") == "origin/task/1"


def test_remove_other_workspace_without_commits(repository):
    repository.create_task("1つ目").start()
    git(repository.root, "switch", "--quiet", "main")
    repository.create_task("2つ目").start()
    result = repository.remove_workspace(1)
    assert result.switched_to is None and result.remote  # 作った時点でGitHubにある
    assert git(repository.root, "branch", "--show-current") == "task/2"
    assert code_of(lambda: repository.remove_workspace(1)) == ErrorCode.BRANCH_NOT_FOUND


def test_another_clone_resumes_with_recorded_base(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    repository.create_branch("develop")
    workspace = repository.create_task("別の場所で続ける").start(base="develop")
    commit_file(workspace, repository.root, "a.txt", "a\n", "途中")
    workspace.push()
    repository.edit_task(1, body="内容を書き直す")  # 本文を直しても作成元の記録は残る
    assert repository.github.issues[1].body.startswith("内容を書き直す")

    other_root = tmp_path / "other"
    git(tmp_path, "clone", "--quiet", str(remote), str(other_root))
    other = Repository(other_root, github=repository.github, command="ecobuild")
    resumed = other.task(1).start()
    assert resumed.base == "develop" and (other_root / "a.txt").exists()


def test_start_leaves_nothing_when_push_fails(repository, remote_and_clone):
    remote, _ = remote_and_clone
    task = repository.create_task("GitHubに置けない")
    (remote / "hooks" / "pre-receive").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
    with pytest.raises(WorkError):
        task.start()
    assert not repository.git.has_local_branch("task/1") and repository.git.current_branch() == "main"
