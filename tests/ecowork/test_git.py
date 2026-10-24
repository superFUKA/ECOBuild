import pytest

from helpers import git, remove_tree, write
from ecowork.git import Git
from ecowork.errors import ErrorCode, WorkError

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
    repo.set_config("branch.task/7.ecowork-base", "develop")
    assert repo.get_config("branch.task/7.ecowork-base") == "develop"
    repo.unset_config("branch.task/7.ecowork-base")
    assert repo.get_config("branch.task/7.ecowork-base") is None


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
    with pytest.raises(WorkError) as error:
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
    with pytest.raises(WorkError) as error:
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
    with pytest.raises(WorkError) as error:
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


def test_push_rejected_when_remote_has_other_commits(remote_and_clone):
    """コミットを書き換えた後の通常のpushは、gitのメッセージでなく次の操作の案内で止まる。"""
    _, work = remote_and_clone
    repo = Git(work, command="ecobuild")
    repo.create_branch("task/7", "main", switch=True)
    write(work / "a.cpp", "int a;\n")
    repo.add(all=True)
    repo.commit("a を追加")
    repo.push("task/7", set_upstream=True)
    repo.commit("a を追加（直し）", all=True, amend=True, allow_empty=True)
    with pytest.raises(WorkError) as error:
        repo.push("task/7")
    assert error.value.code == ErrorCode.NOT_FAST_FORWARD
    assert "ecobuild sync" in error.value.hint and "ecobuild task push --force" in error.value.hint
    repo.push("task/7", force=True)


def test_conflict_markers(remote_and_clone):
    _, work = remote_and_clone
    repo = Git(work)
    write(work / "a.cpp", "int a;\n<<<<<<< HEAD\nint b;\n=======\nint c;\n>>>>>>> origin/main\n")
    repo.add(all=True)
    assert repo.conflict_markers(cached=True) == ("a.cpp:2", "a.cpp:4", "a.cpp:6")
    repo.commit("印が残った")
    assert repo.conflict_markers("HEAD~1...HEAD") == ("a.cpp:2", "a.cpp:4", "a.cpp:6")
    assert repo.conflict_markers(cached=True) == ()


def test_fetch_reuse_skips_a_fetch_just_made(remote_and_clone, monkeypatch):
    """読むだけの処理の fetch(reuse=True) は、このオブジェクトか別のコマンドが取得したばかりなら取得し直さない。"""
    _, work = remote_and_clone
    repo = Git(work)
    fetches = []
    run = repo.run
    monkeypatch.setattr(repo, "run", lambda *args, **kw: (fetches.append(args) if args[0] == "fetch" else None) or run(*args, **kw))
    repo.fetch(reuse=True)
    repo.fetch(reuse=True)
    assert len(fetches) == 1
    other = Git(work)   # 別のコマンド（取得した時刻は .git に残る）
    monkeypatch.setattr(other, "run", lambda *args, **kw: (fetches.append(args) if args[0] == "fetch" else None) or run(*args, **kw))
    other.fetch(reuse=True)
    assert len(fetches) == 1
    other.fetch()           # reuse なしは必ず取得する
    assert len(fetches) == 2


def test_writing_the_shared_config_waits_while_another_workspace_holds_its_lock(repository, monkeypatch):
    """作業空間どうしは .git/config を共有する：ほかが書いている最中（config.lock）なら、待ってやり直す。"""
    import ecowork.git as _git
    monkeypatch.setattr(_git.time, "sleep", lambda seconds: None)
    real = repository.git.run
    failures = []

    def run(*args, **options):
        if args[:2] == ("config", "--local") and len(failures) < 2:
            failures.append(args)
            from dataclasses import replace
            return replace(real("config", "--local", "--get", "no.such-key", check=False),
                           stderr="error: could not lock config file .git/config: File exists")
        return real(*args, **options)
    monkeypatch.setattr(repository.git, "run", run)
    repository.git.set_config("ecowork.test", "1")
    assert len(failures) == 2 and repository.git.get_config("ecowork.test") == "1"


@pytest.mark.needs_git_2_48
def test_forget_missing_worktrees_leaves_worktrees_it_cannot_see(remote_and_clone):
    """元の clone の作業ツリーが見えない環境（コンテナに共有の .git と自分の作業空間だけを付けたとき）では、ほかの
    作業空間も見えないだけなので、ロック付きの記録を消さない。元の clone が見えれば、フォルダーがない記録を片付ける。"""
    _, work = remote_and_clone
    main = Git(work)
    main.create_branch("a", "main", switch=False)
    main.create_branch("b", "main", switch=False)
    main.worktree_add(work / ".w" / "a", "a")
    main.worktree_add(work / ".w" / "b", "b")
    remove_tree(work / ".w" / "b")
    for name in git(work, "ls-tree", "--name-only", "HEAD").splitlines():   # 元の clone の取り出したファイルが見えない
        (work / name).unlink()
    inside = Git(work / ".w" / "a")
    assert not inside.sees_main_worktree()
    assert inside.forget_missing_worktrees() == []
    assert "b" in inside.checked_out_branches() and len(main.worktrees()) == 3
    git(work, "checkout", "--", ".")
    assert inside.sees_main_worktree()
    assert [p.name for p in inside.forget_missing_worktrees()] == ["b"]
    assert "b" not in inside.checked_out_branches() and len(main.worktrees()) == 2
