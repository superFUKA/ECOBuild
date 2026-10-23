import pytest

from helpers import git, write
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def test_task_start_creates_workspace(repository):
    task = repository.create_task("0除算対策", body="divide(1,0)")
    task_branch = task.start()
    assert (task_branch.number, task_branch.branch, task_branch.base) == (task.number, "task/1", "main")
    assert repository.current_task_branch() == task_branch
    status = repository.status()
    assert status.task == 1 and status.branch == "task/1" and status.pull_request is None


def test_commit_only_in_workspace(repository):
    assert repository.current_task_branch() is None
    assert code_of(lambda: repository.require_task_branch("コミット")) == ErrorCode.NOT_ON_TASK_BRANCH
    task_branch = repository.create_task("t").start()
    write(repository.root / "a.cpp", "int a;\n")
    assert task_branch.stage("a.cpp").staged == ("a.cpp",)
    result = task_branch.commit("a を追加")
    assert result.branch == "task/1" and len(result.sha) == 40
    planned = task_branch.push(dry_run=True)                       # 送らずに、送るコミットを返す
    assert not planned.pushed and [c.split(" ", 1)[1] for c in planned.commits] == ["a を追加"]
    remote = repository.remote_url
    assert git(repository.root, "ls-remote", remote, "task/1").split()[0] != result.sha
    assert task_branch.push().commits == planned.commits
    assert git(repository.root, "ls-remote", remote, "task/1").split()[0] == result.sha
    write(repository.root / "b.cpp", "int b;\n")
    task_branch.stage("b.cpp")
    task_branch.commit("b を追加")
    assert [c.split(" ", 1)[1] for c in task_branch.push(dry_run=True).commits] == ["b を追加"]   # GitHubのこのブランチにないもの


def test_start_refuses_uncommitted_changes(repository):
    write(repository.root / "README.md", "changed\n")
    task = repository.create_task("t")
    assert code_of(task.start) == ErrorCode.DIRTY_WORKING_TREE


def test_start_from_another_branch(repository):
    develop = repository.create_branch("develop")
    assert (develop.name, develop.is_task_branch, develop.local, develop.remote) == ("develop", False, True, True)
    task_branch = repository.create_task("t").start(base="develop")
    assert task_branch.base == "develop"
    # 別のIssueのタスクブランチはタスクブランチからは作れない
    second = repository.create_task("u")
    assert code_of(lambda: second.start(base="task/1")) == ErrorCode.INVALID_BASE


def test_resume_existing_workspace(repository):
    first = repository.create_task("t").start()
    git(repository.root, "switch", "--quiet", "main")
    again = repository.task(first.number).start()
    assert again.branch == first.branch


def test_branch_rules(repository):
    assert code_of(lambda: repository.create_branch("task/9")) == ErrorCode.RESERVED_BRANCH_NAME
    assert code_of(lambda: repository.create_branch("x", base="nothing")) == ErrorCode.BRANCH_NOT_FOUND
    repository.create_branch("develop")
    assert code_of(lambda: repository.create_branch("develop")) == ErrorCode.ALREADY_EXISTS
    assert code_of(lambda: repository.branch("main").delete()) == ErrorCode.PROTECTED_BRANCH
    repository.create_task("t").start(base="develop")
    assert code_of(lambda: repository.branch("develop").delete()) == ErrorCode.PROTECTED_BRANCH
    assert code_of(lambda: repository.branch("task/1").delete()) == ErrorCode.PROTECTED_BRANCH
    repository.create_branch("release")
    repository.branch("release").delete()
    names = {b.name for b in repository.branches()}
    assert "release" not in names and {"main", "develop", "task/1"} <= names


def test_local_only_branch_tells_if_merged(repository):
    git(repository.root, "branch", "old")                          # main のまま：取り込み済み
    git(repository.root, "switch", "-q", "-c", "wip")
    write(repository.root / "w.txt", "w\n")
    git(repository.root, "add", "w.txt")
    git(repository.root, "commit", "-q", "-m", "w")                # main にないコミット：取り込んでいない
    git(repository.root, "switch", "-q", "main")
    branches = {b.name: b for b in repository.branches()}
    assert (branches["old"].merged, branches["wip"].merged, branches["main"].merged) == (True, False, None)


def test_closed_task_cannot_start(repository):
    task = repository.create_task("t")
    repository.github.close_issue(repository.root, task.number)
    assert code_of(repository.task(task.number).start) == ErrorCode.TASK_CLOSED


def test_commit_without_staged_changes(repository):
    from helpers import write
    task_branch = repository.create_task("t").start()
    assert code_of(lambda: task_branch.commit("空")) == ErrorCode.NOTHING_TO_COMMIT
    write(repository.root / "README.md", "changed\n")
    assert code_of(lambda: task_branch.commit("未ステージ")) == ErrorCode.NOTHING_TO_COMMIT
    task_branch.commit("追跡中の変更", all=True)
    task_branch.commit("やり直し", amend=True)  # 変更がなくても書き換えはできる


def test_status_reports_deleted_upstream(repository, remote_and_clone):
    """別の場所でタスクブランチのGitHubのブランチが消された（task drop等）ことを status で示す。"""
    remote, _ = remote_and_clone
    task_branch = repository.create_task("t").start()
    write(repository.root / "a.txt", "a\n")
    task_branch.stage("a.txt")
    task_branch.commit("a")
    task_branch.push()
    assert not repository.status().upstream_gone
    git(remote, "branch", "-D", "task/1")
    repository.git.fetch()
    assert repository.status().upstream_gone


def test_start_existing_workspace_fast_forwards(repository, remote_and_clone, tmp_path):
    """手元に古いタスクブランチがあるとき、task start で別の場所からpushされた続きを取り込む。"""
    remote, _ = remote_and_clone
    task_branch = repository.create_task("t").start()
    write(repository.root / "a.txt", "a\n")
    task_branch.stage("a.txt")
    task_branch.commit("a")
    task_branch.push()
    other = tmp_path / "other"
    git(tmp_path, "clone", "--quiet", "--branch", "task/1", str(remote), str(other))
    write(other / "b.txt", "b\n")
    git(other, "add", "b.txt")
    git(other, "commit", "--quiet", "-m", "b")
    git(other, "push", "--quiet", "origin", "task/1")
    repository.task(1).start()
    assert (repository.root / "b.txt").exists()


def test_clone_repository(repository, tmp_path):
    from ecowork import Repository
    target = tmp_path / "second"
    target.mkdir()
    cloned = Repository.clone("remote", directory=target, github=repository.github, command="ecobuild")
    assert cloned.root == (target / "remote").resolve() and (cloned.root / "README.md").exists()
    assert cloned.status().branch == "main"
    assert code_of(lambda: Repository.clone("remote", directory=target, github=repository.github)) \
        == ErrorCode.ALREADY_EXISTS
    assert code_of(lambda: Repository.clone("nosuch", directory=target, github=repository.github)) \
        == ErrorCode.REPOSITORY_NOT_FOUND


def test_hooks_block_direct_commit_and_push(repository, remote_and_clone):
    """gitを直接使っても、タスクブランチでないブランチへはコミット・pushできない（ルールではなく仕組みで）。"""
    import os
    import subprocess
    remote, _ = remote_and_clone
    root = repository.root
    env = {k: v for k, v in os.environ.items() if k != "ECOWORK_ALLOW"}

    def raw(*args):
        return subprocess.run(["git", *args], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8")

    task_branch = repository.create_task("t").start()  # 作業を始めるときにフックを入れる
    hooks = repository.git.hooks_directory()
    assert (hooks / "pre-commit").exists() and (hooks / "pre-push").exists()
    write(root / "a.txt", "a\n")
    task_branch.stage("a.txt")
    assert raw("commit", "-m", "タスクブランチでは通る").returncode == 0
    assert raw("push", "--quiet", "origin", "task/1:task/1").returncode == 0
    git(root, "switch", "--quiet", "main")
    write(root / "b.txt", "b\n")
    raw("add", "b.txt")
    result = raw("commit", "-m", "mainへ直接")
    assert result.returncode != 0 and "直接コミットできません" in result.stderr
    result = raw("push", "origin", "task/1:main")
    assert result.returncode != 0 and "直接pushできません" in result.stderr
    assert raw("push", "origin", "--delete", "main").returncode != 0
    # 利用者のフックは上書きしない
    (hooks / "pre-commit").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert repository.install_hooks() == ()


def test_hooks_remove_ai_attribution(repository):
    """コミットのメッセージからAIの署名を消す（人の Co-Authored-By・本文は残す）。ECOBuild を通しても、gitを直接使っても。"""
    import os
    import subprocess
    root = repository.root
    env = {k: v for k, v in os.environ.items() if k != "ECOWORK_ALLOW"}
    task_branch = repository.create_task("t").start()
    message = ("直した\n\nカーソルの位置を直した（generated by the cursor code は残す）\n\n"
               "Co-Authored-By: Hanako <hanako@example.com>\n"
               "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n"
               "co-authored-by: GitHub Copilot <copilot@github.com>\n\n"
               "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n")
    write(root / "a.txt", "a\n")
    task_branch.stage("a.txt")
    subprocess.run(["git", "commit", "--quiet", "-m", message], cwd=root, env=env, check=True)
    body = git(root, "log", "-1", "--format=%B").strip()
    assert body == ("直した\n\nカーソルの位置を直した（generated by the cursor code は残す）\n\n"
                    "Co-Authored-By: Hanako <hanako@example.com>")
    write(root / "b.txt", "b\n")
    repository.git.run("add", "b.txt")
    repository.git.commit("二つめ\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    assert git(root, "log", "-1", "--format=%B").strip() == "二つめ"
