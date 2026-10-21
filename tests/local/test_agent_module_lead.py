"""モジュールの進行役（ecobuild_agent.module_lead）：タスクを持たない専用の作業空間で、管理役を作る。"""

import json

import pytest

from fakes import FakeGitHub
import ecobuild_container as container
from ecobuild import workspaces
from ecobuild_agent import module_lead as facilitator
from ecobuild_agent import team
from ecobuild_agent.errors import ErrorCode
from ecobuild_bundle import Module
from ecobuild_cli import _effects
from ecowork import WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


@pytest.fixture
def module(tmp_path, monkeypatch):
    from ecowork import github as ecowork_github
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    github = FakeGitHub(tmp_path / "gh")
    monkeypatch.setattr(ecowork_github, "default", lambda: github)
    return Module.create("Plain", directory=tmp_path, type="generic", github=github)


def test_the_facilitator_has_its_own_workspace_without_a_task(module, tmp_path):
    place = facilitator.prepare(module)
    root = facilitator.directory(module)
    assert place.root == root and root.is_relative_to(tmp_path / "home" / "agents" / "modules")
    assert place.repository.git.current_branch() == module.config.default_base      # 作成元の clone・タスクブランチでない
    assert container.enabled(root)                                                  # コンテナ必須
    assert team.is_module_place(root) and team.role_of(root) == team.LEAD
    assert not any(workspaces.same(item.path, root) for item in workspaces.recorded())   # 人の作業空間の一覧に出さない
    assert place.repository.git.working_tree().untracked == ()                      # 印は .ecobuild/ai（除外）の中
    assert code_of(lambda: team.role_of(root, team.WORKER)) == ErrorCode.INVALID_ARGUMENT

    again = facilitator.prepare(module)                                             # 2回目は同じ場所を最新に
    assert again.root == root
    seen = facilitator.place_status(module)
    assert seen.exists and seen.branch == module.config.default_base and not seen.running and seen.members == ()


def test_the_facilitator_is_told_to_talk_and_hand_work_to_a_manager(module):
    place = facilitator.prepare(module)
    assert place._task_for_agent() is None                                           # タスクは要らない
    briefing = place.agent_briefing(None, team.LEAD)
    assert "あなたの役：進行役" in briefing and "モジュールの進行役として" in briefing
    assert "--manager" in briefing and "agent team send" in briefing
    assert "branch create/delete/merge/protect" in briefing and "「はい」" in briefing
    assert "タスクブランチ `" not in briefing


def test_the_facilitators_settings_guard_the_shell_and_the_files(module, tmp_path):
    place = facilitator.prepare(module)
    place._status_settings(tmp_path, True, app=True, role=team.LEAD)
    hooks = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    commands = {entry["matcher"]: entry["hooks"][0]["command"] for entry in hooks}
    assert commands["Bash"].endswith("agent guard --role module")
    assert "lead-edit" in commands["Edit|Write|MultiEdit|NotebookEdit"]


def test_the_facilitator_makes_a_manager_with_a_task_of_its_own(module):
    place = facilitator.prepare(module)
    assert code_of(lambda: team.create(place, "直接", "x", role=team.WORKER)) == ErrorCode.INVALID_ARGUMENT   # 作業役は管理役が作る
    member = team.create(place, "ログイン", "目的：ログインを作る", role=team.MANAGER)
    assert member.role == team.MANAGER and member.path.parent == place.root / team.TEAM_AREA
    task = module.repository.task(member.task)
    assert task.title == "ログイン"
    manager = Module.find(member.path)
    assert manager.require_task_branch("x").base == module.config.default_base      # 親なし：作成元から
    assert team.role_of(manager.root) == team.MANAGER
    assert [m.name for m in facilitator.place_status(module).members] == ["ログイン"]
    assert code_of(lambda: facilitator.close(module)) == ErrorCode.AGENT_ERROR       # 管理役が残っている


def test_the_facilitator_can_be_closed(module):
    facilitator.prepare(module)
    closed = facilitator.close(module)
    assert closed.done and not facilitator.directory(module).exists()
    assert not facilitator.place_status(module).exists


def _hook(command, reply="", prompt="", tmp_path=None):
    transcript = ""
    if tmp_path is not None:
        log = tmp_path / "t.jsonl"
        log.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in (
            {"type": "assistant", "message": {"content": [{"type": "text", "text": reply}]}},
            {"type": "user", "message": {"content": prompt}})) + "\n", encoding="utf-8")
        transcript = str(log)
    data = json.dumps({"tool_input": {"command": command}, "transcript_path": transcript})
    return facilitator.guard(data, _effects.classify_module_lead, program="ecobuild")


def test_the_facilitators_guard(tmp_path):
    assert _hook("ecobuild task list")[0] == 0
    assert _hook("ecobuild branch create release")[0] == 0                          # 変える（戻せる）は自由
    assert _hook("ecobuild agent team start ログイン --manager --brief x")[0] == 0               # チームの操作は進行役の仕事
    assert _hook("ecobuild agent team send ログイン 次の仕事")[0] == 0
    assert _hook("git log --oneline -5 && git diff HEAD~1")[0] == 0
    assert _hook("gh pr list")[0] == 0
    assert _hook("ecobuild task start 3")[0] == 2                                    # タスクブランチの作業は管理役へ
    assert _hook("ecobuild task new 題 --start --name 題")[0] == 2
    assert _hook("git commit -m x")[0] == 2 and _hook("git branch -D x")[0] == 2
    assert _hook("gh api -X DELETE repos/a/b")[0] == 2 and _hook("gh pr merge 3")[0] == 2
    code, message = _hook("ecobuild branch delete release")
    assert code == 2 and "「はい」" in message                                         # 重い操作は人の「はい」
    assert _hook("ecobuild branch delete release", "ecobuild branch delete release を実行してよいですか？", "はい",
                 tmp_path)[0] == 0
