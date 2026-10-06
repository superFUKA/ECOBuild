import pytest

from helpers import git, write
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def push_from_other_clone(remote, tmp_path, name, text, branch="main"):
    other = tmp_path / "other"
    if not other.exists():
        git(tmp_path, "clone", "--quiet", str(remote), str(other))
    git(other, "switch", "--quiet", branch)
    git(other, "pull", "--quiet")
    write(other / name, text)
    git(other, "add", "--all")
    git(other, "commit", "--quiet", "-m", f"{name} を変更")
    git(other, "push", "--quiet", "origin", branch)


def test_sync_fast_forwards_main(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    push_from_other_clone(remote, tmp_path, "new.txt", "new\n")
    result = repository.sync()
    assert result.branch == "main" and result.merged == ("origin/main",) and result.extra is None
    assert (repository.root / "new.txt").exists()
    assert repository.sync().merged == ()


def test_sync_workspace_merges_base_and_resolves_conflict(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    workspace = repository.create_task("t").start()
    write(repository.root / "README.md", "local\n")
    workspace.stage("README.md")
    workspace.commit("手元の変更")
    push_from_other_clone(remote, tmp_path, "README.md", "remote\n")
    assert code_of(repository.sync) == ErrorCode.MERGE_CONFLICT
    status = repository.status()
    assert status.merging and status.conflicted == ("README.md",)
    assert code_of(repository.sync) == ErrorCode.MERGE_CONFLICT  # 止まっている間は再実行できない
    assert code_of(repository.continue_sync) == ErrorCode.MERGE_CONFLICT  # 未解決
    write(repository.root / "README.md", "resolved\n")
    workspace.stage("README.md")
    repository.continue_sync()
    assert not repository.status().merging
    assert code_of(repository.continue_sync) == ErrorCode.NO_SYNC_IN_PROGRESS


def test_sync_abort(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    workspace = repository.create_task("t").start()
    write(repository.root / "README.md", "local\n")
    workspace.stage("README.md")
    workspace.commit("手元の変更")
    push_from_other_clone(remote, tmp_path, "README.md", "remote\n")
    assert code_of(repository.sync) == ErrorCode.MERGE_CONFLICT
    repository.abort_sync()
    assert (repository.root / "README.md").read_text(encoding="utf-8") == "local\n"
    assert code_of(repository.abort_sync) == ErrorCode.NO_SYNC_IN_PROGRESS


def test_sync_stops_when_changes_would_be_overwritten_then_stash(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    push_from_other_clone(remote, tmp_path, "README.md", "remote\n")
    write(repository.root / "README.md", "uncommitted\n")
    assert code_of(repository.sync) == ErrorCode.LOCAL_CHANGES_WOULD_BE_OVERWRITTEN
    stashed = repository.stash()
    assert stashed.stashed and len(repository.stashes()) == 1
    repository.sync()
    assert code_of(repository.stash_pop) == ErrorCode.MERGE_CONFLICT
    assert repository.stashes()  # 衝突時は退避した変更が残る
    repository.restore("README.md", staged=True)
    repository.restore("README.md")
    assert (repository.root / "README.md").read_text(encoding="utf-8") == "remote\n"


def test_continue_after_rebuild_conflict(repository):
    """作業空間の作り直し（rebase）が衝突で止まった場合も、sync continue で続けられる。"""
    root = repository.root
    workspace = repository.create_task("t").start()
    write(root / "a.txt", "1\n")
    workspace.stage("a.txt")
    workspace.commit("1")
    git(root, "switch", "--quiet", "main")
    write(root / "a.txt", "main\n")
    git(root, "add", "a.txt")
    git(root, "commit", "--quiet", "-m", "main側")
    git(root, "switch", "--quiet", "task/1")
    completed = repository.git.rebase_onto("main", "main~1", "task/1")
    assert not completed.merged and repository.git.is_rebasing()
    write(root / "a.txt", "resolved\n")
    workspace.stage("a.txt")
    assert repository.continue_sync().merged == ("rebase",)
    assert not repository.git.is_rebasing()
