import pytest

from helpers import git, write
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def commit_file(task_branch, root, name, text, message):
    write(root / name, text)
    task_branch.stage(name)
    return task_branch.commit(message)


def test_full_cycle_submit_merge_clean(repository):
    root, github = repository.root, repository.github
    task_branch = repository.create_task("0除算対策").start()
    assert code_of(task_branch.submit) == ErrorCode.NOTHING_TO_SUBMIT
    commit_file(task_branch, root, "calc.cpp", "int calc;\n", "計算を追加")
    pr = task_branch.submit()
    assert (pr.head, pr.base, pr.title, pr.partial) == ("task/1", "main", "0除算対策", False)
    assert github.pulls[pr.number].body.startswith("Closes #1")
    # 2回目のsubmitは同じPRを返す
    commit_file(task_branch, root, "calc.cpp", "int calc = 0;\n", "修正")
    assert task_branch.submit().number == pr.number
    assert repository.pull_request().number == pr.number

    result = repository.pull_request().merge()
    assert (result.method, result.closed_issue) == ("squash", 1)
    assert github.issues[1].state == "closed"
    git(root, "fetch", "--quiet", "--prune")
    assert "origin/task/1" not in git(root, "branch", "-r")
    assert code_of(lambda: repository.pull_request(pr.number).merge()) == ErrorCode.PULL_REQUEST_NOT_OPEN

    preview = repository.prune_task_branches(dry_run=True)
    assert preview.removed == ("task/1",) and git(root, "branch", "--show-current") == "task/1"
    cleaned = repository.prune_task_branches()
    assert cleaned.removed == ("task/1",) and cleaned.switched_to == "main"
    assert git(root, "branch", "--show-current") == "main"
    assert (root / "calc.cpp").read_text(encoding="utf-8") == "int calc = 0;\n"  # mainが最新になった
    assert "task/1" not in git(root, "branch")


def test_partial_merge_rebuilds_workspace(repository):
    root, github = repository.root, repository.github
    task_branch = repository.create_task("大きな作業").start()
    commit_file(task_branch, root, "a.txt", "1\n", "前半")
    pr = task_branch.submit(partial=True)
    assert pr.partial and github.pulls[pr.number].body.startswith("Refs #1")
    commit_file(task_branch, root, "b.txt", "2\n", "続き（未push）")
    result = pr.merge()
    assert result.branch_rebuilt and result.closed_issue is None
    assert github.issues[1].state == "open"
    git(root, "fetch", "--quiet")
    # 作り直したタスクブランチには、PRに含まれなかった続きだけが残る
    assert git(root, "log", "--format=%s", "origin/main..task/1").splitlines() == ["続き（未push）"]
    second = repository.current_task_branch().submit()
    assert git(root, "diff", "--name-only", "origin/main", "origin/task/1").splitlines() == ["b.txt"]
    assert second.number != pr.number


def test_branch_to_branch_flow(repository):
    root, github = repository.root, repository.github
    repository.create_branch("develop")
    task_branch = repository.create_task("機能").start(base="develop")
    commit_file(task_branch, root, "f.txt", "f\n", "機能")
    pr = task_branch.submit()
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
    task_branch = repository.create_task("t").start()
    commit_file(task_branch, root, "x.txt", "x\n", "未push")
    github.close_issue(root, task_branch.number)
    result = repository.prune_task_branches()
    assert result.removed == () and result.skipped[0].branch == "task/1"


def test_submit_refuses_committed_conflict_markers(repository):
    root = repository.root
    task_branch = repository.create_task("t").start()
    commit_file(task_branch, root, "a.cpp", "<<<<<<< HEAD\nint a;\n=======\nint b;\n>>>>>>> origin/main\n", "印")
    with pytest.raises(WorkError) as error:
        task_branch.submit()
    assert error.value.code == ErrorCode.CONFLICT_MARKERS and len(error.value.details) == 3
    assert repository.github.pulls == {}
    commit_file(task_branch, root, "a.cpp", "int a;\n", "印を取り除く")
    assert task_branch.submit().number


def test_merge_conflicting_pull_request_guides_sync(repository):
    """作成元と衝突するPRは、マージできない理由と sync での解決を案内する。"""
    root = repository.root
    first = repository.create_task("a").start()
    commit_file(first, root, "README.md", "a\n", "a")
    first.submit()
    git(root, "switch", "--quiet", "main")
    second = repository.create_task("b").start()
    commit_file(second, root, "README.md", "b\n", "b")
    pr = second.submit()
    repository.pull_request(1 + 1).merge()  # 先のPR（#2）
    with pytest.raises(WorkError) as error:
        repository.pull_request(pr.number).merge()
    assert error.value.code == ErrorCode.PULL_REQUEST_CONFLICT
    assert "ecobuild sync" in error.value.hint and "ecobuild task push" in error.value.hint


def test_clean_after_other_clone_merged_shared_workspace(repository, remote_and_clone, tmp_path):
    """2つのcloneで同じタスクブランチにpushし、片方がマージした後、もう片方も片付けられる。"""
    from ecowork import Repository
    remote, _ = remote_and_clone
    other_root = tmp_path / "other"
    git(tmp_path, "clone", "--quiet", str(remote), str(other_root))
    other = Repository(other_root, github=repository.github, command="ecobuild")
    task = repository.create_task("共同作業")
    mine = task.start()
    commit_file(mine, repository.root, "a.txt", "a\n", "a")
    mine.push()
    theirs = other.task(task.number).start()
    commit_file(theirs, other_root, "b.txt", "b\n", "b")
    theirs.push()
    commit_file(mine, repository.root, "c.txt", "c\n", "c")
    repository.sync()  # もう片方のpushを取り込む（マージコミットは手元だけ）
    mine.submit()
    repository.pull_request().merge()
    assert other.prune_task_branches().removed == ("task/1",)


def test_submit_switches_an_open_submission_between_partial_and_final(repository):
    """提出済みでも、取り込まれたらタスクを閉じるか（Refs／Closes）を変えられる。指定しなければそのまま。"""
    root, github = repository.root, repository.github
    task_branch = repository.create_task("切り替え").start()
    commit_file(task_branch, root, "a.txt", "1\n", "前半")
    pr = task_branch.submit(partial=True)
    assert github.pulls[pr.number].body.startswith("Refs #1")
    assert task_branch.submit().partial                      # 送り直しだけ：中間提出のまま
    switched = task_branch.submit(partial=False)
    assert switched.number == pr.number and not switched.partial
    assert github.pulls[pr.number].body.startswith("Closes #1")
    assert task_branch.submit(partial=True).partial and github.pulls[pr.number].body.startswith("Refs #1")


def test_submit_sections_are_replaced_on_resubmit(repository):
    """呼び出し側の節（提出の説明・確認の結果）は、出し直しのたびに差し替わる。人が書き足した部分は残る。"""
    root, github = repository.root, repository.github
    task_branch = repository.create_task("節").start()
    commit_file(task_branch, root, "a.txt", "1\n", "a")
    pr = task_branch.submit(sections={"note": "説明1", "check": "確認 v1"})
    body = github.pulls[pr.number].body
    assert body.startswith("Closes #1") and body.index("説明1") < body.index("確認 v1")
    github.edit_pull_request(root, pr.number, body=body + "\n人のメモ\n")
    commit_file(task_branch, root, "a.txt", "2\n", "b")
    task_branch.submit(sections={"check": "確認 v2"})
    body = github.pulls[pr.number].body
    assert "確認 v1" not in body and "確認 v2" in body and "説明1" in body and "人のメモ" in body
    task_branch.submit(partial=True, sections={"note": ""})
    body = github.pulls[pr.number].body
    assert body.startswith("Refs #1") and "説明1" not in body and "ecowork-section: note" not in body


def test_prune_remote_removes_closed_task_branches_left_only_on_github(repository):
    """手元にない、GitHubだけに残った閉じたタスクのタスクブランチ（--remote）：中身が作成元に入っていれば消す
    （手で取り込んでコミットが別のものでも）、入っていなければ残す。開いているタスクには触らない。"""
    root, github = repository.root, repository.github
    numbers = []
    for title, name, text in (("取り込んでいない", "a.txt", "a\n"), ("手で取り込んだ", "b.txt", "b\n"), ("作業中", "c.txt", "c\n")):
        task_branch = repository.create_task(title).start()
        commit_file(task_branch, root, name, text, title)
        task_branch.push()
        numbers.append(task_branch.number)
        repository.prune_task_branch(task_branch.number)      # 開いているうちに手元の写しだけ消す（別の作業空間で作った形）
    lost, merged, open_ = numbers
    git(root, "switch", "--quiet", "main")
    write(root / "b.txt", "b\n")
    git(root, "add", "b.txt")
    git(root, "commit", "--quiet", "-m", "手で取り込み")
    git(root, "push", "--quiet", "origin", "main")
    github.close_issue(root, lost)
    github.close_issue(root, merged)

    assert repository.prune_task_branches(remote=False).removed == ()          # 既定は手元のものだけ
    preview = repository.prune_task_branches(dry_run=True, remote=True)
    assert preview.removed == (f"task/{merged}",)
    assert [s.branch for s in preview.skipped] == [f"task/{lost}"] and "task drop" in preview.skipped[0].reason
    assert f"origin/task/{merged}" in git(root, "branch", "-r")                 # dry-run は消さない
    assert repository.prune_task_branches(remote=True).removed == (f"task/{merged}",)
    remote = git(root, "ls-remote", "--heads", "origin")
    assert f"task/{merged}" not in remote and f"task/{lost}" in remote and f"task/{open_}" in remote
