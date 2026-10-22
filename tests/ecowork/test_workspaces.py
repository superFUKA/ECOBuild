"""作業空間（git worktree）：タスクブランチを元の clone の外の場所に取り出す。元の clone のブランチはその場で切り替えない。

作業空間は相対パスで記録する（git 2.48 以上。needs_git_2_48）。場所は利用側が決める（ここでは tmp_path の下）。
"""

import pytest

from helpers import git, write
from ecowork import Hooks, Repository
from ecowork import git as _git
from ecowork.errors import ErrorCode, WorkError
from ecowork.git import Git, same_path

pytestmark = [pytest.mark.local, pytest.mark.needs_git_2_48]


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def head_of(root):
    return git(root, "symbolic-ref", "--short", "HEAD")


def started(repository, place, title="t", **options):
    task = repository.create_task(title)
    return task, repository.start_task_in(task.number, place, **options)


def recorded(workspace, name="a.txt", text="a\n", message="a"):
    write(workspace.root / name, text)
    return workspace.current_task_branch().record(message)


# 作る・返す ----------------------------------------------------------------------------

def test_workspace_is_recorded_with_relative_paths_and_locked(repository, tmp_path):
    _, started_ = started(repository, repository.root / ".ecobuild" / "w" / "1")
    place = started_.workspace
    assert started_.created and (started_.number, started_.branch, started_.base) == (1, "task/1", "main")
    gitdir = (place / ".git").read_text(encoding="utf-8").strip()
    assert gitdir.startswith("gitdir: ") and not gitdir.split(" ", 1)[1].startswith(("/", "C:", "c:"))
    assert git(repository.root, "config", "--get", "extensions.relativeWorktrees") == "true"
    assert git(repository.root, "config", "--get", "worktree.useRelativePaths") == "true"
    worktrees = repository.git.worktrees()
    assert [w.main for w in worktrees] == [True, False]
    assert worktrees[1].branch == "task/1" and worktrees[1].locked and same_path(worktrees[1].path, place)
    assert started_.repository.git.is_linked_worktree() and not repository.git.is_linked_worktree()
    assert same_path(started_.repository.git.common_root(), repository.root)
    assert same_path(repository.git.checked_out_branches()["task/1"], place)
    assert same_path(started_.repository.git.hooks_directory(), repository.git.hooks_directory())   # フックは共有
    repository.git.worktree_remove(place)
    assert not place.exists() and len(repository.git.worktrees()) == 1


def test_the_original_clone_never_changes_its_branch(repository, tmp_path):
    """task start・記録・提出・完了・やめる・片付けの間、元の clone の HEAD は main のまま。"""
    _, first = started(repository, tmp_path / "1")
    assert head_of(repository.root) == "main"
    recorded(first.repository)
    first.repository.current_task_branch().submit()
    assert head_of(repository.root) == "main"
    result = repository.finish(1)
    assert result.closed_issue == 1 and result.switched_to is None and same_path(result.workspace_removed, tmp_path / "1")
    _, second = started(repository, tmp_path / "2", title="u")
    assert repository.drop_task(second.number).workspace_removed is not None
    assert head_of(repository.root) == "main" and not repository.git.has_local_branch(second.branch)


def test_start_returns_the_workspace_that_already_has_the_branch(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    _, first = started(repository, tmp_path / "1")
    recorded(first.repository)
    first.repository.current_task_branch().push()
    # 別の場所で push された続きは、作業空間の中で早送りする
    other = tmp_path / "other"
    git(tmp_path, "clone", "--quiet", "--branch", "task/1", str(remote), str(other))
    write(other / "b.txt", "b\n")
    git(other, "add", "b.txt")
    git(other, "commit", "--quiet", "-m", "b")
    git(other, "push", "--quiet", "origin", "task/1")
    again = repository.start_task_in(1, tmp_path / "elsewhere")
    assert not again.created and same_path(again.workspace, tmp_path / "1") and not (tmp_path / "elsewhere").exists()
    assert (tmp_path / "1" / "b.txt").exists()


def test_start_is_refused_when_the_original_clone_has_the_branch(repository, tmp_path):
    task = repository.create_task("t")
    task.start()                                   # 前からの、その場で切り替えた元の clone
    with pytest.raises(WorkError) as error:
        repository.start_task_in(task.number, tmp_path / "1")
    assert error.value.code == ErrorCode.BRANCH_CHECKED_OUT and "元の clone が task/1 を取り出しています" in error.value.message
    assert f"switch main" in error.value.hint and not (tmp_path / "1").exists()


def test_start_from_inside_a_workspace_places_the_new_one_where_asked(repository, tmp_path):
    _, first = started(repository, tmp_path / "1")
    second_task = repository.create_task("u")
    second = first.repository.start_task_in(second_task.number, tmp_path / "2")
    assert second.created and first.repository.git.current_branch() == "task/1"
    assert second.repository.current_task_branch().number == second_task.number


def test_in_place_start_refuses_a_branch_held_by_a_workspace(repository, tmp_path):
    started(repository, tmp_path / "1")
    assert code_of(repository.task(1).start) == ErrorCode.BRANCH_CHECKED_OUT
    assert head_of(repository.root) == "main"


def test_git_older_than_2_48_is_a_clear_error(repository, tmp_path, monkeypatch):
    monkeypatch.setattr(_git, "git_version", lambda executable="git": (2, 45, 1))
    with pytest.raises(WorkError) as error:
        repository.start_task_in(repository.create_task("t").number, tmp_path / "1")
    assert error.value.code == ErrorCode.GIT_ERROR and "git 2.48 以上が必要です" in error.value.message
    assert error.value.hint == "ecobuild setup --install" and not (tmp_path / "1").exists()


def test_git_version_reads_the_windows_form(monkeypatch):
    from ecotask.process import Completed
    monkeypatch.setattr(_git._process, "run",
                        lambda *a, **k: Completed(("git", "--version"), 0, "git version 2.45.1.windows.1\n", ""))
    assert _git.git_version() == (2, 45, 1)
    monkeypatch.setattr(_git._process, "run", lambda *a, **k: Completed(("git", "--version"), 0, "git version 2.48\n", ""))
    assert _git.git_version() == (2, 48, 0)


# 消す ------------------------------------------------------------------------------------

class Removing(Hooks):
    """利用側の作業空間の消し方（ecobuild はロック・コンテナ・記録の片付けと一緒に消す）を真似る。"""

    def __init__(self, refuse=None):
        self.removed, self.refuse = [], refuse

    def remove_workspace(self, repository, path, *, discard):
        if self.refuse:
            raise WorkError(ErrorCode.WORKSPACE_LOCKED, self.refuse)
        self.removed.append((path, discard))
        return super().remove_workspace(repository, path, discard=discard)


def test_finish_inside_the_workspace_removes_it_and_moves_to_the_original(repository, tmp_path):
    _, first = started(repository, tmp_path / "1")
    inside = Repository(first.workspace, github=repository.github, command="ecobuild", hooks=Removing())
    recorded(inside)
    result = inside.finish()
    assert result.removed and same_path(result.workspace_removed, tmp_path / "1") and not (tmp_path / "1").exists()
    assert inside.hooks.removed and same_path(inside.root, repository.root)   # 消した場所でなく元の clone で続く
    assert not repository.git.has_local_branch("task/1") and head_of(repository.root) == "main"


def test_finish_keeps_a_workspace_that_cannot_be_removed(repository, tmp_path):
    _, first = started(repository, tmp_path / "1")
    recorded(first.repository)
    repository.hooks = Removing(refuse="エージェントが動いています")
    result = repository.finish(1)
    assert result.closed_issue == 1 and not result.removed and result.workspace_removed is None
    assert "エージェントが動いています" in result.workspace_kept and (tmp_path / "1").exists()
    assert repository.git.has_local_branch("task/1") and any("残しました" in n for n in repository.notices)


def test_finish_keeps_a_workspace_with_uncommitted_changes(repository, tmp_path):
    _, first = started(repository, tmp_path / "1")
    recorded(first.repository)
    first.repository.current_task_branch().submit()
    write(tmp_path / "1" / "a.txt", "変えた\n")
    result = repository.finish(1)
    assert not result.removed and "未コミットの変更" in result.workspace_kept and (tmp_path / "1" / "a.txt").exists()


def test_drop_dry_run_tells_the_workspace_and_drop_removes_it(repository, tmp_path):
    _, first = started(repository, tmp_path / "1")
    recorded(first.repository)
    preview = repository.drop_task(1, dry_run=True)
    assert same_path(preview.workspace_removed, tmp_path / "1") and (tmp_path / "1").exists()
    write(tmp_path / "1" / "a.txt", "変えた\n")
    assert code_of(lambda: repository.drop_task(1, discard=True)) == ErrorCode.DIRTY_WORKING_TREE
    git(tmp_path / "1", "checkout", "--", "a.txt")
    result = repository.drop_task(1, discard=True)
    assert same_path(result.workspace_removed, tmp_path / "1") and not (tmp_path / "1").exists()
    assert not repository.git.has_local_branch("task/1") and not repository.git.has_remote_branch("task/1")


def test_remove_and_prune_remove_the_workspace(repository, tmp_path):
    _, first = started(repository, tmp_path / "1")
    recorded(first.repository)
    first.repository.current_task_branch().push()
    removed = repository.remove_task_branch(1)
    assert same_path(removed.workspace_removed, tmp_path / "1") and removed.switched_to is None
    assert not repository.git.has_local_branch("task/1")
    again = repository.start_task_in(1, tmp_path / "1")      # GitHub から再開できる
    assert again.created and (tmp_path / "1" / "a.txt").exists()
    repository.github.close_issue(repository.root, 1)
    git(repository.root, "push", "--quiet", "origin", "--delete", "task/1")
    inside = Repository(again.workspace, github=repository.github, command="ecobuild")
    kept = inside.prune_task_branches()            # 取り込んでいないコミットがあれば、作業空間ごと残す
    assert [s.branch for s in kept.skipped] == ["task/1"] and kept.workspace_removed is None and again.workspace.exists()
    _, second = started(repository, tmp_path / "2", title="u")
    repository.github.close_issue(repository.root, second.number)
    result = repository.prune_task_branches(only=second.number)
    assert result.removed == (second.branch,) and [same_path(p, tmp_path / "2") for p in result.workspaces_removed] == [True]
    assert result.workspace_removed is None and not (tmp_path / "2").exists()   # この場所（元の clone）のものではない


def test_prune_inside_the_workspace_removes_it(repository, tmp_path):
    _, first = started(repository, tmp_path / "1")
    repository.github.close_issue(repository.root, 1)
    inside = Repository(first.workspace, github=repository.github, command="ecobuild")
    preview = inside.prune_task_branches(dry_run=True)
    assert preview.removed == ("task/1",) and same_path(preview.workspace_removed, tmp_path / "1")
    assert (tmp_path / "1").exists()
    result = inside.prune_task_branches()
    assert result.removed == ("task/1",) and same_path(result.workspace_removed, tmp_path / "1")
    assert not (tmp_path / "1").exists() and same_path(inside.root, repository.root)


def test_a_branch_held_by_a_workspace_cannot_be_deleted_as_a_branch(repository, tmp_path):
    develop = repository.create_branch("develop")
    repository.git.worktree_add(tmp_path / "d", "develop")
    with pytest.raises(WorkError) as error:
        repository.branch("develop").delete()
    assert error.value.code == ErrorCode.BRANCH_CHECKED_OUT and develop.name == "develop"


def test_tidy_leaves_branches_held_by_workspaces_and_prunes_missing_ones(repository, tmp_path):
    _, first = started(repository, tmp_path / "1")
    git(repository.root, "push", "--quiet", "origin", "--delete", "task/1")
    repository.github.close_issue(repository.root, 1)
    repository.git.fetch()
    assert repository._tidy_finished() == () and repository.git.has_local_branch("task/1")
    git(repository.root, "worktree", "unlock", str(tmp_path / "1"))
    from helpers import remove_tree
    remove_tree(tmp_path / "1")                     # 手で消したフォルダー：記録は prune で片付く
    assert repository._tidy_finished() == ("task/1",) and len(repository.git.worktrees()) == 1


# 中間提出の後の作り直し ---------------------------------------------------------------------

def test_partial_merge_rebuilds_inside_the_workspace(repository, tmp_path):
    _, first = started(repository, tmp_path / "1")
    inside = first.repository
    recorded(inside)
    inside.current_task_branch().submit(partial=True)
    result = repository.finish(1)
    assert result.partial and result.branch_rebuilt and head_of(repository.root) == "main"
    assert git(tmp_path / "1", "rev-parse", "HEAD") == git(repository.root, "rev-parse", "origin/main")


def test_partial_merge_rebuilds_without_a_workspace(repository, tmp_path):
    """取り出している作業ツリーがなければ、作業ツリーに触れずに載せ替える（git replay）。"""
    _, first = started(repository, tmp_path / "1")
    inside = first.repository
    recorded(inside)
    pr = inside.current_task_branch().submit(partial=True)
    repository.github.merge_pull_request(repository.root, pr.number, squash=True, subject="中間 (#2)")
    merged_head = repository.github.pulls[pr.number].head_sha
    recorded(inside, "c.txt", "c\n", "続き")         # 中間提出に入らなかった続き
    inside.current_task_branch().push()
    repository.git.worktree_remove(tmp_path / "1")
    repository.git.fetch()
    assert repository._rebuild_task_branch("task/1", merged_head)
    assert head_of(repository.root) == "main"
    assert git(repository.root, "log", "--format=%s", "origin/main..task/1") == "続き"
    assert git(repository.root, "rev-parse", "task/1~1") == git(repository.root, "rev-parse", "origin/main")
    assert git(repository.root, "rev-parse", "origin/task/1") == git(repository.root, "rev-parse", "task/1")


# 作業空間ごとの設定・退避 ----------------------------------------------------------------------

def test_worktree_config_does_not_leak_into_other_workspaces(repository, tmp_path):
    _, first = started(repository, tmp_path / "1")
    _, second = started(repository, tmp_path / "2", title="u")
    first.repository.git.config_worktree("ecowork.account", "helper-ai")
    assert first.repository.git.get_config("ecowork.account") == "helper-ai"
    assert second.repository.git.get_config("ecowork.account") is None
    assert repository.git.get_config("ecowork.account") is None
    git(repository.root, "config", "--local", "ecowork.account", "shared")
    assert second.repository.git.get_config("ecowork.account") == "shared"     # 共有の設定は既定
    assert first.repository.git.get_config("ecowork.account") == "helper-ai"   # 作業空間のものが勝つ


def test_stash_does_not_pop_another_workspaces_changes(repository, tmp_path):
    _, first = started(repository, tmp_path / "1")
    _, second = started(repository, tmp_path / "2", title="u")
    write(tmp_path / "1" / "one.txt", "1\n")
    first.repository.stash()
    write(tmp_path / "2" / "two.txt", "2\n")
    second.repository.stash()
    first.repository.stash_pop()                      # 最後のもの（2 のもの）ではなく、自分のもの
    assert (tmp_path / "1" / "one.txt").exists() and not (tmp_path / "1" / "two.txt").exists()
    assert len(repository.stashes()) == 1
    write(tmp_path / "1" / "again.txt", "a\n")
    first.repository.stash()
    first.repository.stash_drop()                     # 捨てるのも自分のものだけ
    assert [m.split(":", 1)[0].split(" on ")[-1] for m in repository.stashes()] == [second.branch]
    assert code_of(first.repository.stash_pop) == ErrorCode.UNFINISHED_WORK


# 依存先の clone（作業空間を持たない clone）は今どおりその場で切り替える -------------------------------

def test_a_dependency_clone_still_switches_in_place(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    dependency = tmp_path / "work" / "deps" / "X"
    git(tmp_path, "clone", "--quiet", str(remote), str(dependency))
    clone = Repository(dependency, github=repository.github, command="ecobuild")
    task = clone.create_task("依存先の作業版")
    task_branch = task.start()
    assert head_of(dependency) == task_branch.branch and clone.git.worktrees()[0].main
    write(dependency / "x.txt", "x\n")
    task_branch.record("x")
    result = clone.finish(task.number)
    assert result.removed and result.switched_to == "main" and head_of(dependency) == "main"
    assert result.workspace_removed is None
