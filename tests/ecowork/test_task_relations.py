"""タスクの親子・依存・マイルストーンと、作業の流れとの連動。偽のGitHub＋手元のbareで確かめる。"""

import pytest

from helpers import write
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def finish(repository, number, name):
    task_branch = repository.task(number).start()
    write(repository.root / name, "x\n")
    task_branch.stage(name)
    task_branch.commit(name)
    task_branch.submit()
    result = repository.pull_request().merge()
    repository.prune_task_branches()
    return result


def test_relations_are_shown_and_ready_tasks_are_listed(repository):
    repository.create_milestone("v1", due="2026-10-31")
    parent = repository.create_task("親")
    first = repository.create_task("先", parent=parent.number)
    second = repository.create_task("後", parent=parent.number, blocked_by=(first.number,), milestone="v1")
    listed = {t.number: t for t in repository.tasks()}
    assert (listed[parent.number].subtasks, listed[parent.number].subtasks_done) == (2, 0)
    assert (listed[second.number].parent, listed[second.number].blocked_by,
            listed[second.number].milestone) == (parent.number, 1, "v1")
    assert [t.number for t in repository.tasks(ready=True)] == [first.number]
    assert [t.number for t in repository.tasks(milestone="v1")] == [second.number]

    status = repository.task_status(second.number)
    assert status.parent.number == parent.number and [b.number for b in status.blocked_by] == [first.number]
    assert [s.number for s in repository.task_status(parent.number).subtasks] == [first.number, second.number]
    assert [b.number for b in repository.task_status(first.number).blocking] == [second.number]


def test_subtasks_branch_from_the_parent_workspace(repository):
    """子タスクのタスクブランチは親のタスクブランチから派生し、PRは親のタスクブランチへ。子が終わらないと親は終了できない。"""
    parent = repository.create_task("親")
    first = repository.create_task("先", parent=parent.number)
    second = repository.create_task("後", parent=parent.number, blocked_by=(first.number,))
    parent_branch = f"task/{parent.number}-親"   # 親のタスクブランチの名前は親の題名から
    assert code_of(lambda: repository.task(second.number).start()) == ErrorCode.TASK_BLOCKED
    assert code_of(lambda: repository.close_task(parent.number)) == ErrorCode.OPEN_SUBTASKS
    assert code_of(lambda: repository.task(first.number).start(base="main")) == ErrorCode.INVALID_BASE

    task_branch = repository.task(first.number).start()           # 親のタスクブランチは、なければGitHubに作る
    assert task_branch.base == parent_branch and repository.git.has_remote_branch(parent_branch)
    assert any(parent_branch in n for n in repository.notices)
    write(repository.root / "a.txt", "x\n")
    task_branch.stage("a.txt")
    task_branch.commit("a")
    pr = task_branch.submit()
    assert pr.base == parent_branch
    assert repository.pull_request().merge().closed_issue == first.number    # 親のタスクブランチへ入れて子を閉じる
    repository.prune_task_branches()
    assert not any("すべて閉じました" in n for n in repository.notices)   # 子がまだ残っている

    task_branch = repository.task(second.number).start()
    assert task_branch.base == parent_branch and (repository.root / "a.txt").exists()   # 親の最新から
    write(repository.root / "b.txt", "y\n")
    task_branch.stage("b.txt")
    task_branch.commit("b")
    task_branch.submit()

    parent_workspace = repository.task(parent.number).start()   # 親も作業できる（作成元は main）
    assert parent_workspace.base == "main" and (repository.root / "a.txt").exists()
    write(repository.root / "p.txt", "p\n")
    parent_workspace.stage("p.txt")
    parent_workspace.commit("p")
    repository.notices.clear()
    parent_pr = parent_workspace.submit()
    assert any("子タスクが終わるまで完了できません" in n for n in repository.notices)
    assert code_of(lambda: parent_pr.merge()) == ErrorCode.OPEN_SUBTASKS
    assert code_of(lambda: repository.drop_task(parent.number, close=True, discard=True)) == ErrorCode.OPEN_SUBTASKS

    repository.task(second.number).start()
    repository.pull_request().merge()
    assert any(f"#{parent.number}" in n and "すべて閉じました" in n for n in repository.notices)
    repository.task(parent.number).start()
    repository.sync()                                            # 子の変更を親の手元へ
    assert (repository.root / "b.txt").exists()
    result = repository.pull_request().merge()
    assert result.closed_issue == parent.number
    repository.prune_task_branches()
    repository.sync()
    assert all((repository.root / name).exists() for name in ("a.txt", "b.txt", "p.txt"))


def test_subtask_is_not_started_without_the_parents_unpushed_commits(repository):
    """子のタスクブランチは GitHub の親から作るので、手元の親に GitHub にないコミットがあれば、黙って抜かさずに止める。
    親を push すれば、そのコミットを含めて作る。GitHub にある子のタスクブランチから再開するときは止めない。"""
    parent = repository.create_task("親")
    child = repository.create_task("子", parent=parent.number)
    parent_branch = repository.task(parent.number).start()
    write(repository.root / "p.txt", "p\n")
    parent_branch.stage("p.txt")
    parent_branch.commit("p")                                  # まだ push していない
    with pytest.raises(WorkError) as error:
        repository.task(child.number).start()
    assert error.value.code == ErrorCode.UNFINISHED_WORK and "1 件" in error.value.message
    assert "task push" in error.value.hint and f"task start {child.number}" in error.value.hint
    assert not repository.git.has_local_branch(f"task/{child.number}-子")   # 何も作っていない
    parent_branch.push()
    started = repository.task(child.number).start()
    assert started.base == parent_branch.branch and (repository.root / "p.txt").exists()   # 親のコミットが入る

    repository.task(parent.number).start()                   # 親にまた GitHub にないコミット
    write(repository.root / "q.txt", "q\n")
    parent_branch.stage("q.txt")
    parent_branch.commit("q")
    repository.prune_task_branch(child.number)                # 子の手元を消し、GitHub から再開する
    assert repository.task(child.number).start().base == parent_branch.branch


def test_grandchild_is_not_started_without_the_grandparents_unpushed_commits(repository):
    """孫を始めるとき、GitHub にない親のタスクブランチを祖父から作る。手元の祖父に GitHub にないコミットがあれば止める。
    手元と GitHub が分かれていれば、それを言って sync を案内する。"""
    grand = repository.create_task("祖父")
    parent = repository.create_task("親", parent=grand.number)
    child = repository.create_task("孫", parent=parent.number)
    grand_branch = repository.task(grand.number).start()
    write(repository.root / "g.txt", "g\n")
    grand_branch.stage("g.txt")
    grand_branch.commit("g")
    with pytest.raises(WorkError) as error:
        repository.task(child.number).start()
    assert error.value.code == ErrorCode.UNFINISHED_WORK and grand_branch.branch in error.value.message
    assert not repository.git.has_remote_branch(f"task/{parent.number}-親")   # 親も作っていない

    repository.git.run("commit", "--quiet", "--allow-empty", "-m", "GitHub だけの変更")   # 分かれた状態を作る
    repository.git.run("push", "--quiet", "origin", f"HEAD:refs/heads/{grand_branch.branch}")
    repository.git.run("reset", "--quiet", "--hard", "HEAD~1")
    write(repository.root / "h.txt", "h\n")
    grand_branch.stage("h.txt")
    grand_branch.commit("h")
    repository.git.fetch()
    with pytest.raises(WorkError) as error:
        repository.task(child.number).start()
    assert "分かれています" in error.value.message and "sync" in error.value.hint


def test_parent_without_code_is_closed_after_subtasks(repository):
    """コードを変えない親（タスクブランチなし）は、子が終わってから task close で閉じる。"""
    parent = repository.create_task("親")
    child = repository.create_task("子", parent=parent.number)
    assert code_of(lambda: repository.close_task(parent.number)) == ErrorCode.OPEN_SUBTASKS
    repository.close_task(child.number)
    assert repository.close_task(parent.number).state == "closed"


def test_blocked_task_can_be_started_explicitly(repository):
    first = repository.create_task("先")
    second = repository.create_task("後", blocked_by=(first.number,))
    task_branch = repository.task(second.number).start(ignore_blocked=True)
    assert task_branch.number == second.number
    # 一度始めたタスクブランチへ戻るときは止めない
    repository.task(first.number).start()
    assert repository.task(second.number).start().number == second.number



def test_subtask_waits_while_its_parent_waits(repository):
    """親（親の親も）が先行タスクを待っている間は、子も始められない（子を始めると親も始まるため）。"""
    first = repository.create_task("先")
    parent = repository.create_task("親", blocked_by=(first.number,))
    child = repository.create_task("子", parent=parent.number)
    grandchild = repository.create_task("孫", parent=child.number)
    with pytest.raises(WorkError) as error:
        repository.task(grandchild.number).start()
    assert error.value.code == ErrorCode.TASK_BLOCKED and f"#{parent.number}" in error.value.message
    assert any(f"#{first.number}" in d and f"#{parent.number} が待っている" in d for d in error.value.details)
    assert code_of(lambda: repository.task(child.number).start()) == ErrorCode.TASK_BLOCKED
    assert code_of(lambda: repository.start_task_without_branch(child.number)) == ErrorCode.TASK_BLOCKED
    assert [t.number for t in repository.tasks(ready=True)] == [first.number]

    repository.close_task(first.number)
    assert repository.task(grandchild.number).start().number == grandchild.number   # 待ちが解ければ親も一緒に始まる

def test_editing_relations(repository):
    one, two, three = (repository.create_task(t) for t in ("一", "二", "三"))
    repository.edit_task(three.number, parent=one.number, add_blocked_by=(two.number,))
    assert code_of(lambda: repository.edit_task(three.number, parent=two.number)) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: repository.edit_task(three.number, parent=three.number)) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: repository.edit_task(three.number, milestone="ない")) == ErrorCode.MILESTONE_NOT_FOUND
    repository.edit_task(three.number, clear_parent=True, parent=two.number)  # 外す＋付ける＝付け替え（1回で）
    assert repository.task_status(three.number).parent.number == two.number
    repository.edit_task(three.number, clear_parent=True, remove_blocked_by=(two.number,))
    status = repository.task_status(three.number)
    assert (status.parent, status.blocked_by) == (None, ())


def test_milestones(repository):
    repository.create_milestone("v1", due="2026-10-31", description="最初")
    assert code_of(lambda: repository.create_milestone("v1")) == ErrorCode.ALREADY_EXISTS
    task = repository.create_task("t", milestone="v1")
    assert task.milestone == "v1"
    renamed = repository.edit_milestone("v1", new_title="v1.0", due="")
    assert (renamed.title, renamed.due) == ("v1.0", None)
    assert repository.task(task.number).milestone == "v1.0"
    assert repository.edit_milestone("v1.0", state="closed").state == "closed"
    assert repository.milestones() == [] and len(repository.milestones(closed=True)) == 1
    assert repository.edit_task(task.number, clear_milestone=True).milestone is None
