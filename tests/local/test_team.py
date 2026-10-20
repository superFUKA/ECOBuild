"""進行役と作業役（ecobuild_bundle.team）：作業役は子タスク＋進行役の作業空間の中の作業空間。"""

import json

import pytest

from fakes import FakeGitHub
from ecobuild import settings, workspaces
from ecobuild.errors import ErrorCode
from ecowork import WorkError
from ecobuild_bundle import Module, team

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


@pytest.fixture
def lead(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    module.repository.create_task("大きな仕事").start(name="大きな仕事")
    return module


def test_a_worker_is_a_child_task_in_the_leads_workspace(lead, monkeypatch):
    settings.set_config("agent_worker_model", "haiku")
    member = team.create(lead, "画面", "目的：ログイン画面を作る\n範囲：src/ui だけ", model="")
    assert member.role == team.WORKER and member.path.parent == lead.root / team.TEAM_AREA
    assert member.path.name == f"{member.task}-画面" and member.branch.startswith(f"task/{member.task}-")
    child = lead.repository.task(member.task)
    assert child.title == "画面"
    assert Module.find(member.path).require_task_branch("x").base == lead.require_task_branch("x").branch   # 親のタスクブランチから
    assert (member.path / team.BRIEF_FILE).read_text(encoding="utf-8").startswith("目的：ログイン画面")
    assert json.loads((member.path / team.MEMBER_FILE).read_text(encoding="utf-8"))["lead"] == str(lead.root)
    assert member.prompt == team.FIRST_PROMPT[team.WORKER]
    assert any(workspaces.same(item.path, member.path) for item in workspaces.recorded())   # 入れ子でも作業空間
    assert not workspaces.nested(member.path)
    assert lead.repository.git.working_tree().untracked == ()                              # 進行役の側は変わらない

    listed = team.team(lead.root)
    assert [m.name for m in listed.members] == ["画面"] and not listed.members[0].reported
    (member.path / team.REPORT_FILE).write_text("できた\n", encoding="utf-8")
    assert team.find(lead.root, str(member.task)).reported
    assert code_of(lambda: team.find(lead.root, "ない")) == ErrorCode.INVALID_ARGUMENT

    worker = Module.find(member.path)
    assert team.role_of(worker.root) == team.WORKER and team.role_of(lead.root) == team.WORKER
    assert team.agent_options(worker.root, team.WORKER, ("claude",)) == ("claude", "--model", "haiku")   # このPCの設定
    assert code_of(lambda: team.create(worker, "もっと", "分ける")) == ErrorCode.INVALID_ARGUMENT        # 作業役は作らない
    briefing = worker.agent_briefing(worker.require_task_branch("x"), team.WORKER)
    assert "作業役" in briefing and team.REPORT_FILE in briefing

    (member.path / team.REPORT_FILE).unlink()
    closed = Module.close_workspace(member.path)                                            # 入れ子でも閉じられる
    assert closed.done and not member.path.exists() and team.team(lead.root).members == ()


def test_a_lead_has_its_own_model_and_cannot_edit(lead):
    settings.set_config("agent_lead_model", "opus")
    assert team.agent_options(lead.root, team.LEAD, ("claude",)) == \
        ("claude", "--model", "opus", "--disallowedTools", "Edit,Write,NotebookEdit")
    assert team.agent_options(lead.root, team.LEAD, ("claude", "--model", "sonnet"))[:3] == ("claude", "--model", "sonnet")
    assert team.agent_options(lead.root, team.LEAD, ("codex",)) == ("codex",)               # Claude Code だけ
    sub = team.create(lead, "下の進行役", "この部分を受け持つ", role=team.LEAD, model="sonnet")
    assert team.role_of(sub.path) == team.LEAD and sub.prompt == team.FIRST_PROMPT[team.LEAD]
    assert team.agent_options(sub.path, team.LEAD, ("claude",))[:3] == ("claude", "--model", "sonnet")   # 作ったときの指定
    briefing = lead.agent_briefing(lead.require_task_branch("x"), team.LEAD)
    assert "進行役" in briefing and "agent team start" in briefing and team.PLAN_FILE in briefing
    assert code_of(lambda: team.create(lead, "空", "  ")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: team.role_of(lead.root, "boss")) == ErrorCode.INVALID_ARGUMENT


def test_the_first_prompt_goes_right_after_claude(lead):
    command = lead._for_role(("claude",), team.LEAD, "始めて")
    assert command[:2] == ("claude", "始めて") and "--disallowedTools" in command   # 値を何個も取る引数に読まれない


def test_requests_are_answered_by_the_gui(lead, monkeypatch, tmp_path):
    """GUI の窓・コンテナの中では、操作を頼みとして書き、GUI が書いた結果を読む。拾われなければ止める。"""
    monkeypatch.setenv(team.WINDOW_VARIABLE, "1")
    assert team.should_forward()
    folder = team.requests_folder(lead.root)

    def gui(seconds):   # 待つたびに、GUI のふりをして頼みに答える
        for request in folder.glob("*.json"):
            if request.name.endswith(".result.json"):
                continue
            data = json.loads(request.read_text(encoding="utf-8"))
            assert data["args"] == ["agent", "team", "list", "--json"] and data["cwd"] == "src"
            request.rename(request.with_suffix(".taken"))
            (folder / f"{data['id']}.result.json").write_text(json.dumps({"ok": True, "result": {"members": []}}),
                                                               encoding="utf-8")
    doc = team.forward(lead.root, ["agent", "team", "list", "--json"], lead.root / "src", wait=gui)
    assert doc == {"ok": True, "result": {"members": []}}

    clock = iter(range(0, 100, 10))
    monkeypatch.setattr(team.time, "monotonic", lambda: next(clock))
    assert code_of(lambda: team.forward(lead.root, ["agent", "team", "list"], lead.root, wait=lambda s: None)) \
        == ErrorCode.AGENT_ERROR
    assert not [p for p in folder.glob("*.json")]                                            # 拾われなかった頼みは消す


def test_a_resumed_conversation_keeps_its_role(lead, monkeypatch):
    """起動のときに会話の ID を決めて役を覚え、続きから起動する（--resume <id>・--continue）ときはその役に戻る。"""
    started = lead._for_role(("claude",), team.LEAD, "")
    session = started[started.index("--session-id") + 1]
    assert team.remembered_roles(lead.root) == {session: team.LEAD}
    assert lead.repository.git.working_tree().untracked == ()                   # 覚えた所はコミットの対象に出ない
    assert lead._role("", ("claude", "--resume", session), False, None, None) == team.LEAD
    assert lead._role("", ("claude", "--resume", "other"), False, None, None) == team.WORKER   # 知らない会話
    assert lead._role("", ("claude", "--resume"), False, None, None) == team.WORKER           # Claude の一覧で選ぶ：分からない
    assert lead._role(team.WORKER, ("claude", "--resume", session), False, None, None) == team.WORKER   # 指定が先
    monkeypatch.setattr(type(lead), "agent_conversations",
                        lambda self, limit=20: type("C", (), {"conversations": [type("X", (), {"id": session})()]})())
    assert lead._role("", ("claude", "--continue"), False, None, None) == team.LEAD          # いちばん新しい会話の役
    resumed = lead._for_role(("claude", "--resume", session), team.LEAD, "")
    assert "--session-id" not in resumed                                         # 続きからは ID を決めない
