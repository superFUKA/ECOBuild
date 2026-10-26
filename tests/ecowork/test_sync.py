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
    task_branch = repository.create_task("t").start()
    write(repository.root / "README.md", "local\n")
    task_branch.stage("README.md")
    task_branch.commit("手元の変更")
    push_from_other_clone(remote, tmp_path, "README.md", "remote\n")
    assert code_of(repository.sync) == ErrorCode.MERGE_CONFLICT
    status = repository.status()
    assert status.merging and status.conflicted == ("README.md",)
    assert code_of(repository.sync) == ErrorCode.MERGE_CONFLICT  # 止まっている間は再実行できない
    assert code_of(repository.continue_sync) == ErrorCode.CONFLICT_MARKERS  # 未解決（印が残っている）
    assert repository.status().conflicted == ("README.md",)                 # 何も登録していない
    write(repository.root / "README.md", "resolved\n")
    repository.continue_sync()     # 直したファイルは自分で登録する（task add は要らない）
    assert not repository.status().merging
    assert (repository.root / "README.md").read_text(encoding="utf-8") == "resolved\n"
    assert code_of(repository.continue_sync) == ErrorCode.NO_SYNC_IN_PROGRESS


def test_continue_sync_records_a_deleted_file(repository, remote_and_clone, tmp_path):
    """衝突したファイルを消して解決したら、削除として登録する。"""
    remote, _ = remote_and_clone
    task_branch = repository.create_task("t").start()
    write(repository.root / "README.md", "local\n")
    task_branch.stage("README.md")
    task_branch.commit("手元の変更")
    push_from_other_clone(remote, tmp_path, "README.md", "remote\n")
    assert code_of(repository.sync) == ErrorCode.MERGE_CONFLICT
    (repository.root / "README.md").unlink()
    repository.continue_sync()
    assert not repository.status().merging
    assert not (repository.root / "README.md").exists()


def test_sync_abort(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    task_branch = repository.create_task("t").start()
    write(repository.root / "README.md", "local\n")
    task_branch.stage("README.md")
    task_branch.commit("手元の変更")
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
    """タスクブランチの作り直し（rebase）が衝突で止まった場合も、sync continue で続けられる。"""
    root = repository.root
    task_branch = repository.create_task("t").start()
    write(root / "a.txt", "1\n")
    task_branch.stage("a.txt")
    task_branch.commit("1")
    git(root, "switch", "--quiet", "main")
    write(root / "a.txt", "main\n")
    git(root, "add", "a.txt")
    git(root, "commit", "--quiet", "-m", "main側")
    git(root, "switch", "--quiet", "task/1")
    completed = repository.git.rebase_onto("main", "main~1", "task/1")
    assert not completed.merged and repository.git.is_rebasing()
    write(root / "a.txt", "resolved\n")
    task_branch.stage("a.txt")
    assert repository.continue_sync().merged == ("rebase",)
    assert not repository.git.is_rebasing()


def _conflict_in_workspace(repository, remote, tmp_path):
    task_branch = repository.create_task("t").start()
    write(repository.root / "README.md", "local\n")
    task_branch.stage("README.md")
    task_branch.commit("手元の変更")
    push_from_other_clone(remote, tmp_path, "README.md", "remote\n")
    assert code_of(repository.sync) == ErrorCode.MERGE_CONFLICT
    return task_branch


def test_continue_refuses_leftover_conflict_markers(repository, remote_and_clone, tmp_path):
    """衝突の印を残したまま登録しても、取り込みを完了しない（仮運用でmainに印が入った）。"""
    remote, _ = remote_and_clone
    task_branch = _conflict_in_workspace(repository, remote, tmp_path)
    task_branch.stage("README.md")  # 直さずに登録
    with pytest.raises(WorkError) as error:
        repository.continue_sync()
    assert error.value.code == ErrorCode.CONFLICT_MARKERS and error.value.details == ["README.md:1", "README.md:3", "README.md:5"]
    assert code_of(lambda: task_branch.commit("取り込み")) == ErrorCode.CONFLICT_MARKERS
    assert repository.status().merging
    write(repository.root / "README.md", "resolved\n")
    assert code_of(lambda: task_branch.commit("取り込み")) == ErrorCode.CONFLICT_MARKERS  # 未登録の分は見ない
    task_branch.commit("取り込み", all=True)
    assert not repository.status().merging


def test_sync_refuses_closed_workspace(repository):
    """反映済み（Issueが閉じた）タスクブランチでは取り込まず、片付けを案内する。"""
    task_branch = repository.create_task("t").start()
    repository.github.close_issue(repository.root, task_branch.number)
    with pytest.raises(WorkError) as error:
        repository.sync()
    assert error.value.code == ErrorCode.TASK_CLOSED and "ecobuild task prune" in error.value.hint


def _stash_pop_conflict(repository, remote, tmp_path):
    write(repository.root / "README.md", "local\n")
    repository.stash()
    push_from_other_clone(remote, tmp_path, "README.md", "remote\n")
    repository.sync()
    with pytest.raises(WorkError) as error:
        repository.stash_pop()
    return error.value


def test_stash_pop_conflict_on_main_continues_then_drop(repository, remote_and_clone, tmp_path):
    """退避した変更の戻しの衝突も、止まっている操作（stash）として sync continue で終える（タスクブランチでない
    ブランチでも）。直したファイルは未コミットの変更になり、退避した変更は stash drop まで残る。"""
    remote, _ = remote_and_clone
    error = _stash_pop_conflict(repository, remote, tmp_path)
    assert "ecobuild sync continue" in error.hint and "ecobuild stash drop" in error.hint
    status = repository.status()
    assert (status.stopped, status.merging) == ("stash", True)
    assert code_of(repository.sync) == ErrorCode.MERGE_CONFLICT                  # 止まっている間は取り込まない
    assert code_of(repository.continue_sync) == ErrorCode.CONFLICT_MARKERS
    write(repository.root / "README.md", "resolved\n")
    assert repository.continue_sync().merged == ()
    status = repository.status()
    assert (status.stopped, status.conflicted, status.staged, status.unstaged) == (None, (), (), ("README.md",))
    assert repository.stash_drop().entries == ()
    assert code_of(repository.stash_drop) == ErrorCode.NO_STASH


def test_stash_pop_conflict_aborts_keeping_the_stash(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    _stash_pop_conflict(repository, remote, tmp_path)
    repository.abort_sync()
    assert (repository.root / "README.md").read_text(encoding="utf-8") == "remote\n"
    assert repository.status().stopped is None and repository.stashes()


def test_take_side_resolves_with_one_side(repository, remote_and_clone, tmp_path):
    """衝突したファイルを、今の側（タスクブランチ）か入ってくる側（作成元）の内容で解決する。"""
    remote, _ = remote_and_clone
    _conflict_in_workspace(repository, remote, tmp_path)
    assert code_of(lambda: repository.take_side(("other.txt",), incoming=True)) == ErrorCode.INVALID_ARGUMENT
    assert repository.take_side((), incoming=True) == ("README.md",)
    assert (repository.root / "README.md").read_text(encoding="utf-8") == "remote\n"
    assert repository.status().conflicted == ()
    repository.continue_sync()
    assert repository.status().stopped is None
    assert code_of(lambda: repository.take_side((), incoming=False)) == ErrorCode.NO_SYNC_IN_PROGRESS


def test_take_side_removes_a_file_deleted_on_that_side(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    task_branch = repository.create_task("t").start()
    write(repository.root / "README.md", "local\n")
    task_branch.record("手元の変更")
    other = tmp_path / "other"
    git(tmp_path, "clone", "--quiet", str(remote), str(other))
    git(other, "rm", "--quiet", "README.md")
    git(other, "commit", "--quiet", "-m", "消した")
    git(other, "push", "--quiet", "origin", "main")
    assert code_of(repository.sync) == ErrorCode.MERGE_CONFLICT
    repository.take_side(("README.md",), incoming=True)
    repository.continue_sync()
    assert not (repository.root / "README.md").exists()


def test_status_and_submit_tell_the_conflicts_with_the_base(repository, remote_and_clone, tmp_path):
    """作成元を取り込む前に、衝突するファイルを知らせる（status --fetch・提出のお知らせ）。手元は変えない。"""
    remote, _ = remote_and_clone
    task_branch = repository.create_task("t").start()
    write(repository.root / "README.md", "local\n")
    task_branch.record("手元の変更")
    push_from_other_clone(remote, tmp_path, "README.md", "remote\n")
    status = repository.status(fetch=True)
    assert (status.base_behind, status.base_conflicts, status.stopped) == (1, ("README.md",), None)
    task_branch.submit()
    assert any("衝突する" in n and "README.md" in n for n in repository.notices)
    assert not repository.git.is_merging()


def test_sync_explains_local_commits_on_main(repository, remote_and_clone, tmp_path):
    """gitを直接使って main にコミットした場合は、ECOBuildの操作では起きないことと、そのコミットを示す。"""
    remote, _ = remote_and_clone
    git(repository.root, "commit", "--quiet", "--allow-empty", "-m", "直接のコミット")
    push_from_other_clone(remote, tmp_path, "new.txt", "new\n")
    with pytest.raises(WorkError) as error:
        repository.sync()
    assert error.value.code == ErrorCode.NOT_FAST_FORWARD and "gitを直接使った" in error.value.hint
    assert [line.split(" ", 1)[1] for line in error.value.details] == ["直接のコミット"]


def test_sync_notices_changes_made_on_github(repository, remote_and_clone):
    """ECOBuildの外（GitHubのサイト等）での変化：アーカイブは知らせる、名前の変更は origin を合わせる、
    作成元のブランチがなくなったら知らせる。"""
    github = repository.github
    github.archived_repositories.append("tester/remote")
    repository.sync()
    assert any("アーカイブ（読み取り専用）" in n and "ecobuild module unarchive tester/remote" in n
               for n in repository.notices)
    assert repository.status(fetch=True).archived is True

    repository.notices.clear()
    git(repository.root, "remote", "set-url", "origin", "https://github.com/tester/old.git")
    assert repository.check_repository() is True
    assert repository.remote_url == "https://github.com/tester/remote.git"
    assert any("tester/old から tester/remote に変わっていた" in n for n in repository.notices)

    repository.notices.clear()
    git(repository.root, "remote", "set-url", "origin", str(remote_and_clone[0]))
    repository.default_base = "develop"
    repository.check_repository()
    assert any("作成元 develop がGitHubにありません" in n and "既定のブランチは main" in n for n in repository.notices)


def _commits(task_branch, root, *changes):
    """（ファイル名, 中身）ごとに1コミット。作ったコミットを返す。"""
    made = []
    for name, text in changes:
        write(root / name, text)
        task_branch.stage(name)
        task_branch.commit(f"{name} を {text.strip()}")
        made.append(git(root, "rev-parse", "HEAD").strip())
    return made


def test_restore_to_an_earlier_version(repository):
    """restore --source：ファイルを以前の版の状態に戻す（未コミットの変更になる。その版になかったファイルは消える）。"""
    root = repository.root
    task_branch = repository.create_task("t").start()
    first, _ = _commits(task_branch, root, ("a.txt", "1\n"), ("a.txt", "2\n"))
    write(root / "b.txt", "b\n"); task_branch.stage("b.txt"); task_branch.commit("b を足す")
    head = git(root, "rev-parse", "HEAD").strip()
    result = repository.restore(source=first[:8])
    assert result.source == first and (root / "a.txt").read_text(encoding="utf-8") == "1\n" and not (root / "b.txt").exists()
    assert git(root, "rev-parse", "HEAD").strip() == head            # 履歴は消さない
    assert repository.status().staged                                   # 戻した結果は、コミットする変更
    # 戻した変更があるうちは、もう一度は戻さない（未コミットの変更が失われるので）
    assert code_of(lambda: repository.restore(source=head)) == ErrorCode.DIRTY_WORKING_TREE
    git(root, "reset", "--quiet", "--hard")
    assert code_of(lambda: repository.restore(source="nosuch")) == ErrorCode.REVISION_NOT_FOUND


def test_restore_discards_staged_changes_and_added_files(repository):
    """restore <ファイル>：最後のコミットの状態にする。ステージした変更も、追加したファイル（ステージ済み・未追跡）も取り消す。"""
    root = repository.root
    task_branch = repository.create_task("t").start()
    _commits(task_branch, root, ("a.txt", "1\n"), ("b.txt", "1\n"))
    write(root / "a.txt", "2\n"); task_branch.stage("a.txt")            # ステージした変更
    write(root / "b.txt", "2\n")                                        # ステージしていない変更
    write(root / "c.txt", "c\n"); task_branch.stage("c.txt")            # 追加してステージしたファイル
    write(root / "d.txt", "d\n")                                        # 未追跡のファイル
    write(root / "e.txt", "e\n")                                        # 名前を挙げない未追跡のファイルは残す
    repository.restore("a.txt", "b.txt", "c.txt", "d.txt")
    assert (root / "a.txt").read_text(encoding="utf-8") == "1\n" and (root / "b.txt").read_text(encoding="utf-8") == "1\n"
    assert not (root / "c.txt").exists() and not (root / "d.txt").exists() and (root / "e.txt").exists()
    status = repository.status()
    assert not status.staged and not status.unstaged and status.untracked == ("e.txt",)


def test_restore_to_a_version_only_on_a_task_branch(repository):
    head = git(repository.root, "rev-parse", "HEAD").strip()
    assert code_of(lambda: repository.restore(source=head)) == ErrorCode.NOT_ON_TASK_BRANCH


def test_reset_task_drops_the_later_commits_not_pushed(repository):
    """task reset：タスクブランチを以前の版まで戻す。push 済みのコミットは捨てない。作成元より前には戻らない。"""
    root = repository.root
    base = git(root, "rev-parse", "HEAD").strip()
    task_branch = repository.create_task("t").start()
    first, second, third = _commits(task_branch, root, ("a.txt", "1\n"), ("a.txt", "2\n"), ("a.txt", "3\n"))
    preview = repository.reset_task(first, dry_run=True)
    assert [sha for sha, _ in preview.dropped] == [third, second] and git(root, "rev-parse", "HEAD").strip() == third
    assert repository.reset_task(second).dropped[0][0] == third
    assert git(root, "rev-parse", "HEAD").strip() == second and (root / "a.txt").read_text(encoding="utf-8") == "2\n"
    assert repository.reset_task(second).dropped == ()                 # もうそこにいる
    assert repository.reset_task(base, dry_run=True).dropped           # タスクの最初（作成元から分かれた所）までは戻せる
    git(root, "push", "--quiet", "origin", "HEAD")                      # push 済み
    assert code_of(lambda: repository.reset_task(first)) == ErrorCode.COMMITS_WOULD_BE_LOST


def test_reset_task_keep_leaves_the_changes(repository):
    """task reset --keep：コミットを取り消し、その変更（と今の変更）はコミットしていない変更として残す。"""
    root = repository.root
    task_branch = repository.create_task("t").start()
    first, second = _commits(task_branch, root, ("a.txt", "1\n"), ("b.txt", "2\n"))
    write(root / "c.txt", "c\n")                                        # 今の変更があっても取り消せる
    result = repository.reset_task(first, keep=True)
    assert result.kept and [sha for sha, _ in result.dropped] == [second]
    assert git(root, "rev-parse", "HEAD").strip() == first
    assert (root / "b.txt").read_text(encoding="utf-8") == "2\n" and (root / "c.txt").exists()
    assert set(repository.status().untracked) >= {"b.txt", "c.txt"}


@pytest.mark.needs_git_2_48
def test_stash_drop_on_the_original_clone_leaves_what_another_worktree_stashed(repository, tmp_path):
    """退避は作業ツリーどうしで共有：元の clone の stash drop は、切り離された作業ツリー（確認用の作業空間）や、ほかの
    作業ツリーが取り出しているブランチで退避したものを選ばない。"""
    repository.git.worktree_add(tmp_path / "r1", detach_at="HEAD")
    write(tmp_path / "r1" / "README.md", "確認中の変更\n")
    git(tmp_path / "r1", "stash", "push", "--quiet")
    repository.git.run("branch", "feature/x")
    repository.git.worktree_add(tmp_path / "fx", "feature/x")
    write(tmp_path / "fx" / "README.md", "ほかの作業ツリー\n")
    git(tmp_path / "fx", "stash", "push", "--quiet")
    assert code_of(repository.stash_drop) == ErrorCode.NO_STASH
    assert len(repository.stashes()) == 2
    write(repository.root / "README.md", "元の clone\n")
    repository.stash()
    repository.stash_drop()
    assert len(repository.stashes()) == 2 and all("main" not in m for m in repository.stashes())


def test_sync_takes_in_another_branch(repository, remote_and_clone, tmp_path):
    """タスクブランチへ、作成元のほかのブランチ（GitHub の別の管理ブランチ等）も取り込む。タスクブランチでないブランチでは止める。"""
    remote, _ = remote_and_clone
    other = tmp_path / "other"
    git(tmp_path, "clone", "--quiet", str(remote), str(other))
    git(other, "switch", "--quiet", "-c", "release")
    git(other, "push", "--quiet", "-u", "origin", "release")
    push_from_other_clone(remote, tmp_path, "release.txt", "release\n", branch="release")
    assert code_of(lambda: repository.sync(from_branch="release")) == ErrorCode.INVALID_ARGUMENT
    repository.create_task("t").start()
    assert code_of(lambda: repository.sync(from_branch="nothing")) == ErrorCode.BRANCH_NOT_FOUND
    result = repository.sync(from_branch="release")
    assert result.merged == ("origin/release",)
    assert (repository.root / "release.txt").read_text(encoding="utf-8") == "release\n"
    assert repository.sync(from_branch="release").merged == ()


def test_sync_takes_in_the_base_at_a_chosen_commit(repository, remote_and_clone, tmp_path):
    """作成元を、最新ではなく選んだコミットまで取り込む。取り込んでいる作成元のバージョンは status の base_at。"""
    remote, _ = remote_and_clone
    task_branch = repository.create_task("t").start()
    write(repository.root / "mine.txt", "mine\n")
    task_branch.record("手元の変更")
    start = repository.status().base_at
    assert start == git(repository.root, "rev-parse", "origin/main").strip()
    push_from_other_clone(remote, tmp_path, "first.txt", "first\n")
    push_from_other_clone(remote, tmp_path, "second.txt", "second\n")
    git(repository.root, "fetch", "--quiet")
    first = git(repository.root, "rev-parse", "origin/main~1").strip()
    assert code_of(lambda: repository.sync(at="HEAD")) == ErrorCode.INVALID_ARGUMENT   # 作成元にないコミット（手元の）
    assert repository.sync(at=first).merged == (f"origin/main@{first[:7]}",)
    assert (repository.root / "first.txt").exists() and not (repository.root / "second.txt").exists()
    assert repository.status().base_at == first
    repository.sync()
    assert (repository.root / "second.txt").exists()
