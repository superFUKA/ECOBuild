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


def _conflict_in_workspace(repository, remote, tmp_path):
    workspace = repository.create_task("t").start()
    write(repository.root / "README.md", "local\n")
    workspace.stage("README.md")
    workspace.commit("手元の変更")
    push_from_other_clone(remote, tmp_path, "README.md", "remote\n")
    assert code_of(repository.sync) == ErrorCode.MERGE_CONFLICT
    return workspace


def test_continue_refuses_leftover_conflict_markers(repository, remote_and_clone, tmp_path):
    """衝突の印を残したまま登録しても、取り込みを完了しない（仮運用でmainに印が入った）。"""
    remote, _ = remote_and_clone
    workspace = _conflict_in_workspace(repository, remote, tmp_path)
    workspace.stage("README.md")  # 直さずに登録
    with pytest.raises(WorkError) as error:
        repository.continue_sync()
    assert error.value.code == ErrorCode.CONFLICT_MARKERS and error.value.details == ["README.md:1", "README.md:3", "README.md:5"]
    assert code_of(lambda: workspace.commit("取り込み")) == ErrorCode.CONFLICT_MARKERS
    assert repository.status().merging
    write(repository.root / "README.md", "resolved\n")
    assert code_of(lambda: workspace.commit("取り込み")) == ErrorCode.CONFLICT_MARKERS  # 未登録の分は見ない
    workspace.commit("取り込み", all=True)
    assert not repository.status().merging


def test_sync_refuses_closed_workspace(repository):
    """反映済み（Issueが閉じた）作業空間では取り込まず、片付けを案内する。"""
    workspace = repository.create_task("t").start()
    repository.github.close_issue(repository.root, workspace.number)
    with pytest.raises(WorkError) as error:
        repository.sync()
    assert error.value.code == ErrorCode.TASK_CLOSED and "ecobuild task clean" in error.value.hint


def test_stash_pop_conflict_on_main_then_drop(repository, remote_and_clone, tmp_path):
    """作業空間でないブランチでは add できないので、restore --staged で解決し、stash drop で片付ける。"""
    remote, _ = remote_and_clone
    write(repository.root / "README.md", "local\n")
    repository.stash()
    push_from_other_clone(remote, tmp_path, "README.md", "remote\n")
    repository.sync()
    with pytest.raises(WorkError) as error:
        repository.stash_pop()
    assert "ecobuild restore --staged" in error.value.hint and "ecobuild stash drop" in error.value.hint
    write(repository.root / "README.md", "resolved\n")
    repository.restore("README.md", staged=True)
    assert repository.status().conflicted == ()
    assert repository.stash_drop().entries == ()
    assert code_of(repository.stash_drop) == ErrorCode.NO_STASH


def test_sync_explains_local_commits_on_main(repository, remote_and_clone, tmp_path):
    """gitを直接使って main にコミットした場合は、ECOBuildの操作では起きないことと、そのコミットを示す。"""
    remote, _ = remote_and_clone
    git(repository.root, "commit", "--quiet", "--allow-empty", "-m", "直接のコミット")
    push_from_other_clone(remote, tmp_path, "new.txt", "new\n")
    with pytest.raises(WorkError) as error:
        repository.sync()
    assert error.value.code == ErrorCode.NOT_FAST_FORWARD and "gitを直接使った" in error.value.hint
    assert [line.split(" ", 1)[1] for line in error.value.details] == ["直接のコミット"]
