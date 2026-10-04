import pytest

from conftest import git, write
from ecobuild._git import Git
from ecobuild.errors import EcoBuildError, ErrorCode

pytestmark = pytest.mark.local


def test_working_tree_reports_changes(remote_and_clone):
    _, work = remote_and_clone
    repo = Git(work)
    assert repo.current_branch() == "main"
    assert repo.working_tree().clean
    write(work / "README.md", "changed\n")
    write(work / "new file.txt", "x\n")
    write(work / "staged.txt", "y\n")
    repo.add(("staged.txt",))
    tree = repo.working_tree()
    assert tree.branch == "main" and tree.upstream == "origin/main"
    assert tree.unstaged == ("README.md",)
    assert tree.staged == ("staged.txt",)
    assert tree.untracked == ("new file.txt",)


def test_branch_commit_push_and_ahead(remote_and_clone):
    remote, work = remote_and_clone
    repo = Git(work)
    repo.create_branch("task/7", "main", switch=True)
    write(work / "a.cpp", "int a;\n")
    repo.add(all=True)
    sha = repo.commit("a を追加")
    assert repo.working_tree().ahead == 0  # 追跡先がまだない
    repo.push("task/7", set_upstream=True)
    assert git(remote, "rev-parse", "task/7") == sha
    write(work / "a.cpp", "int a = 1;\n")
    repo.commit("修正", all=True)
    assert repo.working_tree().ahead == 1
    repo.commit("修正（やり直し）", all=True, amend=True)
    repo.push("task/7", force=True)
    assert git(remote, "rev-parse", "task/7") == repo.rev_parse("HEAD")


def test_branch_config_records_base(remote_and_clone):
    _, work = remote_and_clone
    repo = Git(work)
    repo.set_config("branch.task/7.ecobuild-base", "develop")
    assert repo.get_config("branch.task/7.ecobuild-base") == "develop"
    repo.unset_config("branch.task/7.ecobuild-base")
    assert repo.get_config("branch.task/7.ecobuild-base") is None


def _diverge(remote, work, tmp_path, *, conflict):
    """リモートのmainを別のcloneから進め、手元の作業ブランチでも同じファイルを変える。"""
    other = tmp_path / "other"
    git(tmp_path, "clone", "--quiet", str(remote), str(other))
    write(other / "README.md", "remote\n")
    git(other, "commit", "--quiet", "-am", "remote change")
    git(other, "push", "--quiet", "origin", "main")
    repo = Git(work)
    repo.create_branch("task/7", "main", switch=True)
    write(work / ("README.md" if conflict else "b.txt"), "local\n")
    repo.add(all=True)
    repo.commit("local change")
    repo.fetch()
    return repo


def test_merge_without_conflict(remote_and_clone, tmp_path):
    remote, work = remote_and_clone
    repo = _diverge(remote, work, tmp_path, conflict=False)
    outcome = repo.merge("origin/main")
    assert outcome.merged
    assert (work / "README.md").read_text(encoding="utf-8") == "remote\n"


def test_merge_conflict_continue_and_abort(remote_and_clone, tmp_path):
    remote, work = remote_and_clone
    repo = _diverge(remote, work, tmp_path, conflict=True)
    outcome = repo.merge("origin/main")
    assert not outcome.merged and outcome.conflicted == ("README.md",)
    assert repo.is_merging()
    with pytest.raises(EcoBuildError) as error:
        repo.merge_continue()
    assert error.value.code == ErrorCode.MERGE_CONFLICT
    repo.merge_abort()
    assert not repo.is_merging() and repo.working_tree().clean
    repo.merge("origin/main")
    write(work / "README.md", "resolved\n")
    repo.add(("README.md",))
    repo.merge_continue()
    assert not repo.is_merging()


def test_local_changes_would_be_overwritten(remote_and_clone, tmp_path):
    remote, work = remote_and_clone
    repo = _diverge(remote, work, tmp_path, conflict=False)
    write(work / "README.md", "uncommitted\n")
    with pytest.raises(EcoBuildError) as error:
        repo.merge("origin/main")
    assert error.value.code == ErrorCode.LOCAL_CHANGES_WOULD_BE_OVERWRITTEN


def test_fast_forward_only(remote_and_clone, tmp_path):
    remote, work = remote_and_clone
    repo = _diverge(remote, work, tmp_path, conflict=False)
    repo.switch("main")
    assert repo.merge("origin/main", ff_only=True).merged
    write(work / "c.txt", "c\n")
    repo.add(all=True)
    repo.commit("main に直接")
    other = tmp_path / "other"
    write(other / "d.txt", "d\n")
    git(other, "add", "d.txt")
    git(other, "commit", "--quiet", "-m", "more")
    git(other, "push", "--quiet", "origin", "main")
    repo.fetch()
    with pytest.raises(EcoBuildError) as error:
        repo.merge("origin/main", ff_only=True)
    assert error.value.code == ErrorCode.NOT_FAST_FORWARD


def test_stash_and_restore(remote_and_clone):
    _, work = remote_and_clone
    repo = Git(work)
    write(work / "README.md", "changed\n")
    write(work / "untracked.txt", "u\n")
    assert repo.stash_push("作業途中")
    assert repo.working_tree().clean
    assert [entry.message for entry in repo.stash_list()] == ["On main: 作業途中"]
    assert repo.stash_pop().merged
    assert (work / "untracked.txt").exists()
    repo.restore(("README.md",))
    assert (work / "README.md").read_text(encoding="utf-8") == "seed\n"
    (work / "untracked.txt").unlink()
    assert not repo.stash_push()  # 退避するものがない


def test_rebase_onto_after_squash(remote_and_clone):
    """squashマージ後、PRに含まれなかった続きのコミットだけを作成元の最新へ載せ替える。"""
    _, work = remote_and_clone
    repo = Git(work)
    repo.create_branch("task/7", "main", switch=True)
    write(work / "a.txt", "1\n")
    repo.add(all=True)
    pr_head = repo.commit("PRに含めた")
    write(work / "b.txt", "2\n")
    repo.add(all=True)
    repo.commit("続き")
    # main側でsquashマージを再現
    repo.switch("main")
    git(work, "merge", "--squash", pr_head)
    git(work, "commit", "--quiet", "-m", "PR #1 (squash)")
    outcome = repo.rebase_onto("main", pr_head, "task/7")
    assert outcome.merged
    log = git(work, "log", "--format=%s", "main..task/7").splitlines()
    assert log == ["続き"]
