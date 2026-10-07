import pytest

from helpers import git, write
from fakes import FakeGitHub
from ecowork import Hooks, Repository
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


class Recorder(Hooks):
    def __init__(self, stop_submit=False):
        self.calls = []
        self.stop_submit = stop_submit

    def after_sync(self, repository):
        self.calls.append("after_sync")
        return len(self.calls)

    def before_submit(self, repository):
        self.calls.append("before_submit")
        if self.stop_submit:
            raise WorkError("stopped", "止めました")


def with_hooks(repository, hooks):
    return Repository(repository.root, github=repository.github, command=repository.command, hooks=hooks)


def test_after_sync_result_goes_to_extra(repository):
    hooks = Recorder()
    result = with_hooks(repository, hooks).sync()
    assert hooks.calls == ["after_sync"] and result.extra == 1


def test_after_sync_runs_after_continue_but_not_on_conflict(repository, remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    hooks = Recorder()
    repo = with_hooks(repository, hooks)
    workspace = repo.create_task("t").start()
    write(repo.root / "README.md", "local\n")
    workspace.stage("README.md")
    workspace.commit("手元の変更")
    other = tmp_path / "other"
    git(tmp_path, "clone", "--quiet", str(remote), str(other))
    write(other / "README.md", "remote\n")
    git(other, "commit", "--quiet", "-am", "remote")
    git(other, "push", "--quiet", "origin", "main")
    with pytest.raises(WorkError):
        repo.sync()
    assert hooks.calls == []
    write(repo.root / "README.md", "resolved\n")
    workspace.stage("README.md")
    result = repo.continue_sync()
    assert hooks.calls == ["after_sync"] and result.merged == ("merge",) and result.extra == 1


def test_before_submit_can_stop_before_push(repository):
    hooks = Recorder(stop_submit=True)
    repo = with_hooks(repository, hooks)
    workspace = repo.create_task("t").start()
    write(repo.root / "a.txt", "a\n")
    workspace.stage("a.txt")
    workspace.commit("a")
    with pytest.raises(WorkError) as error:
        workspace.submit()
    assert error.value.code == "stopped" and hooks.calls == ["before_submit"]
    assert repo.git.rev_parse("origin/task/1") != repo.git.rev_parse("task/1") and not repo.github.pulls  # pushしていない


def test_hints_use_command_name(repository):
    with pytest.raises(WorkError) as error:
        repository.require_workspace("コミット")
    assert "ecobuild task start" in error.value.hint
    plain = Repository(repository.root, github=repository.github)
    with pytest.raises(WorkError) as error:
        plain.require_workspace("コミット")
    assert error.value.hint.startswith("task start ")


def test_create_with_populate(tmp_path):
    github = FakeGitHub(tmp_path / "gh")
    repo = Repository.create("Calc", directory=tmp_path, github=github, message="作成",
                             populate=lambda root: write(root / "a.txt", "a\n"))
    assert repo.root == (tmp_path / "Calc").resolve()
    assert git(github.bare, "log", "--format=%s", "main") == "作成"
    assert git(github.bare, "show", "main:a.txt") == "a"
    with pytest.raises(WorkError) as error:
        Repository.create("Calc", directory=tmp_path, github=github)
    assert error.value.code == ErrorCode.ALREADY_EXISTS
