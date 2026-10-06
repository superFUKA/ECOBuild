import pytest

from helpers import git, write
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


def test_full_cycle_submit_merge_clean(repository):
    root, github = repository.root, repository.github
    workspace = repository.create_task("0除算対策").start()
    assert code_of(workspace.submit) == ErrorCode.NOTHING_TO_SUBMIT
    commit_file(workspace, root, "calc.cpp", "int calc;\n", "計算を追加")
    pr = workspace.submit()
    assert (pr.head, pr.base, pr.title, pr.partial) == ("task/1", "main", "0除算対策", False)
    assert github.pulls[pr.number].body.startswith("Closes #1")
    # 2回目のsubmitは同じPRを返す
    commit_file(workspace, root, "calc.cpp", "int calc = 0;\n", "修正")
    assert workspace.submit().number == pr.number
    assert repository.pull_request().number == pr.number

    result = repository.pull_request().merge()
    assert (result.method, result.closed_issue) == ("squash", 1)
    assert github.issues[1].state == "closed"
    git(root, "fetch", "--quiet", "--prune")
    assert "origin/task/1" not in git(root, "branch", "-r")
    assert code_of(lambda: repository.pull_request(pr.number).merge()) == ErrorCode.PULL_REQUEST_NOT_OPEN

    preview = repository.clean_workspaces(dry_run=True)
    assert preview.removed == ("task/1",) and git(root, "branch", "--show-current") == "task/1"
    cleaned = repository.clean_workspaces()
    assert cleaned.removed == ("task/1",) and cleaned.switched_to == "main"
    assert git(root, "branch", "--show-current") == "main"
    assert (root / "calc.cpp").read_text(encoding="utf-8") == "int calc = 0;\n"  # mainが最新になった
    assert "task/1" not in git(root, "branch")


def test_partial_merge_rebuilds_workspace(repository):
    root, github = repository.root, repository.github
    workspace = repository.create_task("大きな作業").start()
    commit_file(workspace, root, "a.txt", "1\n", "前半")
    pr = workspace.submit(partial=True)
    assert pr.partial and github.pulls[pr.number].body.startswith("Refs #1")
    commit_file(workspace, root, "b.txt", "2\n", "続き（未push）")
    result = pr.merge()
    assert result.workspace_rebuilt and result.closed_issue is None
    assert github.issues[1].state == "open"
    git(root, "fetch", "--quiet")
    # 作り直した作業空間には、PRに含まれなかった続きだけが残る
    assert git(root, "log", "--format=%s", "origin/main..task/1").splitlines() == ["続き（未push）"]
    second = repository.current_workspace().submit()
    assert git(root, "diff", "--name-only", "origin/main", "origin/task/1").splitlines() == ["b.txt"]
    assert second.number != pr.number


def test_branch_to_branch_flow(repository):
    root, github = repository.root, repository.github
    repository.create_branch("develop")
    workspace = repository.create_task("機能").start(base="develop")
    commit_file(workspace, root, "f.txt", "f\n", "機能")
    pr = workspace.submit()
    assert pr.base == "develop"
    result = pr.merge()
    # 既定ブランチ以外へのマージでも、ECOBuildがIssueを閉じる
    assert result.closed_issue == 1 and github.issues[1].state == "closed"
    develop = repository.branch("develop")
    assert code_of(lambda: repository.branch("main").submit(into="develop")) == ErrorCode.NOTHING_TO_SUBMIT
    release = develop.submit(into="main")
    assert (release.head, release.base) == ("develop", "main")
    assert release.merge().method == "merge"
    git(root, "fetch", "--quiet")
    assert len(git(root, "log", "--format=%P", "-1", "origin/main").split()) == 2  # マージコミット


def test_clean_keeps_unpushed_work(repository):
    root, github = repository.root, repository.github
    workspace = repository.create_task("t").start()
    commit_file(workspace, root, "x.txt", "x\n", "未push")
    github.close_issue(root, workspace.number)
    result = repository.clean_workspaces()
    assert result.removed == () and result.skipped[0].branch == "task/1"
