"""進行役と作業役（ecobuild_bundle.team）：作業役は子タスク＋進行役の作業空間の中の作業空間。"""

import json
from pathlib import Path

import pytest

from fakes import FakeGitHub
from ecobuild import settings, workspaces
from ecobuild.errors import ErrorCode
from ecowork import WorkError
from ecobuild_bundle import Module, agent_serve, agent_status, container, team

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


def test_requests_are_answered_by_the_serve(lead, monkeypatch, tmp_path):
    """GUI の窓・コンテナの中では、操作を頼みとして書き、係が書いた結果を読む。拾われなければ止める。"""
    monkeypatch.setenv(team.WINDOW_VARIABLE, "1")
    assert team.should_forward()
    folder = team.requests_folder(lead.root)

    def gui(seconds):   # 待つたびに、係のふりをして頼みに答える
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


def test_send_and_the_lead_notice_go_to_the_inbox(lead):
    """言付けは作業役の受け箱に、作業役の返答の終わりは進行役の受け箱に入る（届けるのはエージェントを動かしている側）。"""
    member = team.create(lead, "画面", "目的：画面を作る")
    team.send(lead.root, "画面", "ボタンは右に")
    got = agent_status.take(team.inbox_of(member.path))
    assert got["text"].endswith("ボタンは右に") and got["text"].startswith("[進行役「")
    assert agent_status.take(team.inbox_of(member.path)) is None                       # 取り出したら空
    assert code_of(lambda: team.send(lead.root, "画面", " ")) == ErrorCode.INVALID_ARGUMENT

    where, text = team.lead_notice(member.path, "できました\n  確かめました")
    assert where == lead.root and "作業役「画面」" in text and "まだありません" in text
    assert text.endswith("最後の返答：できました 確かめました")
    (member.path / team.REPORT_FILE).write_text("できた\n", encoding="utf-8")
    assert f"報告：{team.TEAM_AREA}/{member.path.name}/{team.REPORT_FILE}" in team.lead_notice(member.path, "")[1]
    assert team.lead_notice(lead.root, "x") is None                                     # 進行役自身は知らせない


def test_the_serve_answers_requests_and_tells_the_lead(lead):
    """係：頼みを実行して結果を書き戻し、作業役ができたら起動を頼み、作業役の返答の終わりを進行役に知らせる。"""
    member = team.create(lead, "画面", "目的：画面を作る")
    folder = agent_status.prepare(container.name(lead.root), lead.root)
    agent_status.prepare(container.name(member.path), member.path)
    events, ran = [], []

    def run(args, cwd):
        ran.append((args, cwd))
        if args[:3] == ["agent", "team", "start"]:
            return {"ok": True, "result": {"path": str(member.path), "name": "画面", "role": "worker", "prompt": "読んで"}}
        return {"ok": True, "result": {}}

    serve = agent_serve.Serve(run, emit=events.append, ack=lambda key, timeout: True)
    requests = folder / team.REQUESTS
    requests.mkdir()
    (requests / "a.json").write_text(json.dumps({"id": "a", "args": ["agent", "team", "start", "画面", "--json"], "cwd": "."}),
                                     encoding="utf-8")
    (requests / "b.json").write_text(json.dumps({"id": "b", "args": ["task", "finish"], "cwd": "."}), encoding="utf-8")
    (requests / "c.json").write_text(json.dumps({"id": "c", "args": ["agent", "team", "close", "画面"], "cwd": "../.."}),
                                     encoding="utf-8")
    serve.step()
    result = lambda key: json.loads((requests / f"{key}.result.json").read_text(encoding="utf-8"))
    assert result("a")["ok"] and events[0] == {"event": "agent-start", "path": str(member.path), "name": "画面",
                                               "role": "worker", "prompt": "読んで", "lead": str(lead.root)}
    assert not result("b")["ok"] and not result("c")["ok"]                             # チームの操作だけ・作業空間の中だけ
    assert [a for a, _ in ran] == [["agent", "team", "start", "画面", "--json"]]
    assert not list(requests.glob("*.taken"))

    (requests / "d.json").write_text(json.dumps({"id": "d", "args": ["agent", "team", "close", "画面"], "cwd": "."}),
                                     encoding="utf-8")
    serve.step()
    assert events[1]["event"] == "agent-stop" and events[1]["path"] == str(member.path)   # 閉じる前に止めてもらう
    assert ran[-1][0] == ["agent", "team", "close", "画面"]

    member_folder = team.inbox_of(member.path)
    (member_folder / "replied.json").write_text(json.dumps({"at": serve.started + 5, "message": "終わりました"}),
                                                encoding="utf-8")
    serve.step()
    notice = agent_status.take(folder)
    assert "作業役「画面」" in notice["text"] and notice["text"].endswith("終わりました")
    assert ran[-1] == (["project", "update"], member.path)                               # 型に手元をそろえさせる
    serve.step()
    assert agent_status.take(folder) is None                                             # 同じ返答は1回だけ


def test_without_an_app_the_serve_opens_the_worker_itself(lead):
    opened = []
    serve = agent_serve.Serve(lambda args, cwd: {"ok": True, "result": {"path": "/w", "name": "x", "role": "worker",
                                                                       "prompt": "p"}},
                              open_agent=lambda path, role, prompt: opened.append((path, role, prompt)))
    doc = serve.handle(lead.root, {"id": "a", "args": ["agent", "team", "start", "x"], "cwd": "."})
    assert doc["result"]["opened"] and opened == [(Path("/w"), "worker", "p")]


def test_only_one_serve_runs(lead):
    with agent_serve.Lock():
        assert code_of(lambda: agent_serve.Lock().__enter__()) == ErrorCode.AGENT_ERROR
    with agent_serve.Lock():
        pass


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
