"""作業空間のエージェントの関所（ecobuild_agent.guard・ecobuild agent guard）：シェルの ecobuild・gh・git の書き込みを止め、
ほかは通す。手伝いのコミットもここで止まる。"""

import json

import pytest
from click.testing import CliRunner

from ecoagent.guard import check_denied
from ecobuild_agent import guard, inside
from ecobuild_cli import build_cli


def refused(command: str) -> str | None:
    return check_denied(command, guard.DENIED)


@pytest.mark.parametrize("command", [
    'git commit -m "x"', "git -C /work commit -am x", "git push origin HEAD", "git switch main", "git checkout -b x",
    "git reset --hard", "git rebase main", "git merge x", "git worktree add ../x", "git branch -D task/1",
    "git branch new-one", "git tag v1", "git stash", "git stash pop", "git config user.name x",
    "git config --unset core.hooksPath", "git remote add o url", "git -c alias.ci=commit ci", "git update-ref refs/x HEAD",
    "ecobuild task submit", "/usr/local/bin/ecobuild test", "gh pr create", "cd x && git commit -m y",
    'bash -c "git push"', "GIT_DIR=x git commit", "echo $(git push)",
])
def test_writing_git_ecobuild_and_gh_are_stopped(command):
    assert refused(command), command


@pytest.mark.parametrize("command", [
    "git status", "git diff --stat", "git log --oneline -5", "git show HEAD", "git branch", "git branch -a",
    "git branch --list 'task/*'", "git tag", "git tag -l v*", "git stash list", "git config --get user.name",
    "git config user.name", "git remote -v", "git blame a.py", "git -C /work status", "ls && cat a.txt",
    "python -m pytest", "grep -r 'git commit' .", "rm -rf build",
])
def test_reading_and_other_commands_pass(command):
    assert refused(command) is None, command


def test_the_hook_tells_the_agent_to_use_the_tools():
    data = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m 手伝いの変更"}})
    code, message = guard.hook(data)
    assert code == 2 and "git commit" in message and "MCP のツール" in message and "手伝いはコミット" in message
    result = CliRunner().invoke(build_cli(), ["agent", "guard"], input=data)
    assert result.exit_code == 2 and "git commit" in result.stderr
    passed = CliRunner().invoke(build_cli(), ["agent", "guard"], input=json.dumps({"tool_input": {"command": "git status"}}))
    assert passed.exit_code == 0 and passed.stderr == ""


def test_the_managed_settings_deny_the_shell_ways_by_default():
    deny = json.loads(inside.agent_settings(("WebFetch", "Bash(gh:*)")))["permissions"]["deny"]
    assert deny == [*inside.DEFAULT_DENY, "WebFetch"]
    assert {"Bash(ecobuild:*)", "Bash(gh:*)", "Bash(git commit:*)", "Bash(git push:*)", "Bash(git worktree:*)"} <= set(deny)
