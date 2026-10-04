import pytest

from helpers import git, write
from ecobuild.errors import EcoBuildError, ErrorCode

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(EcoBuildError) as error:
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


def test_sync_fast_forwards_main(module, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    push_from_other_clone(remote, tmp_path, "new.txt", "new\n")
    result = module.sync()
    assert result.branch == "main" and result.merged == ("origin/main",) and not result.regenerated
    assert (module.root / "new.txt").exists()
    assert module.sync().merged == ()


def test_sync_workspace_merges_base_and_resolves_conflict(module, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    workspace = module.create_task("t").start()
    write(module.root / "README.md", "local\n")
    workspace.stage("README.md")
    workspace.commit("手元の変更")
    push_from_other_clone(remote, tmp_path, "README.md", "remote\n")
    assert code_of(module.sync) == ErrorCode.MERGE_CONFLICT
    status = module.status()
    assert status.merging and status.conflicted == ("README.md",)
    assert code_of(module.sync) == ErrorCode.MERGE_CONFLICT  # 止まっている間は再実行できない
    assert code_of(module.continue_sync) == ErrorCode.MERGE_CONFLICT  # 未解決
    write(module.root / "README.md", "resolved\n")
    workspace.stage("README.md")
    module.continue_sync()
    assert not module.status().merging
    assert code_of(module.continue_sync) == ErrorCode.NO_SYNC_IN_PROGRESS


def test_sync_abort(module, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    workspace = module.create_task("t").start()
    write(module.root / "README.md", "local\n")
    workspace.stage("README.md")
    workspace.commit("手元の変更")
    push_from_other_clone(remote, tmp_path, "README.md", "remote\n")
    assert code_of(module.sync) == ErrorCode.MERGE_CONFLICT
    module.abort_sync()
    assert (module.root / "README.md").read_text(encoding="utf-8") == "local\n"
    assert code_of(module.abort_sync) == ErrorCode.NO_SYNC_IN_PROGRESS


def test_sync_stops_when_changes_would_be_overwritten_then_stash(module, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    push_from_other_clone(remote, tmp_path, "README.md", "remote\n")
    write(module.root / "README.md", "uncommitted\n")
    assert code_of(module.sync) == ErrorCode.LOCAL_CHANGES_WOULD_BE_OVERWRITTEN
    stashed = module.stash()
    assert stashed.stashed and len(module.stashes()) == 1
    module.sync()
    assert code_of(module.stash_pop) == ErrorCode.MERGE_CONFLICT
    assert module.stashes()  # 衝突時は退避した変更が残る
    module.restore("README.md", staged=True)
    module.restore("README.md")
    assert (module.root / "README.md").read_text(encoding="utf-8") == "remote\n"


def test_continue_after_rebuild_conflict(module):
    """作業空間の作り直し（rebase）が衝突で止まった場合も、sync --continue で続けられる。"""
    root = module.root
    workspace = module.create_task("t").start()
    write(root / "a.txt", "1\n")
    workspace.stage("a.txt")
    workspace.commit("1")
    git(root, "switch", "--quiet", "main")
    write(root / "a.txt", "main\n")
    git(root, "add", "a.txt")
    git(root, "commit", "--quiet", "-m", "main側")
    git(root, "switch", "--quiet", "task/1")
    completed = module._git.rebase_onto("main", "main~1", "task/1")
    assert not completed.merged and module._git.is_rebasing()
    write(root / "a.txt", "resolved\n")
    workspace.stage("a.txt")
    assert module.continue_sync().merged == ("rebase",)
    assert not module._git.is_rebasing()
