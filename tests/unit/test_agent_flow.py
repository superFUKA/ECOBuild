"""流れの agent の工程（ecobuild_agent.flow）：起動（係に頼む start_agent）・様子（status.activity）・止める口を差し替えて。
本物のコンテナ・係は使わない。"""

import json
import time
from types import SimpleNamespace

import pytest

import ecobuild_agent
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_agent import flow as agent_flow
from ecobuild_agent import status
from ecoflow import DONE, FAILED, RUNNING, Engine, Outcome, Store, check, load


class FakeModule:
    """start_agent(app=True) の代わり：起動した（登録の名前・プロンプト）を覚え、記録のようなものを返す。"""

    def __init__(self, root, folder, error=None, interrupt=False):
        self.root = root
        self.folder = folder
        self.started = []
        self.error = error
        self.interrupt = interrupt   # 記録を作った後、係に頼む前に止まる（Ctrl+C）

    def start_agent(self, name, *, app, prompt, progress, recorded=None):
        assert app is True
        if self.error is not None:
            raise self.error
        self.started.append((name, prompt))
        record = SimpleNamespace(id=f"a-{len(self.started):010d}", name=name, folder=self.folder)
        recorded(record)
        if self.interrupt:
            raise KeyboardInterrupt
        return record


class FakeAgent:
    """様子（activity）を、呼ばれた回数で決める。replies：返答を終える回目 → (最後の返答, 結果のファイルに書くもの)。"""

    def __init__(self, replies=None, *, state=status.IDLE, error=""):
        self.replies = dict(replies or {})
        self.calls = 0
        self.state = state
        self.error = error
        self.result_path = None
        self.stopped = []

    def activity(self, folder):
        self.calls += 1
        if self.calls in self.replies:
            reply, result = self.replies[self.calls]
            if result is not None:
                self.result_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            return {"state": self.state, "replied_at": time.time() + 1, "last_reply": reply, "error": self.error}
        if self.state == status.STOPPED:
            return {"state": status.STOPPED, "replied_at": None, "last_reply": "", "error": self.error}
        return {"state": status.WORKING, "replied_at": None, "last_reply": "", "doing": "Edit"}


@pytest.fixture
def agent(monkeypatch, tmp_path):
    fake = FakeAgent()
    monkeypatch.setattr(status, "activity", lambda folder: fake.activity(folder))
    monkeypatch.setattr(ecobuild_agent, "stop_agent", lambda agent_id, progress=None: fake.stopped.append(agent_id))
    monkeypatch.setattr(agent_flow, "POLL", 0.0)
    return fake


def setup(tmp_path, agent, steps, module=None):
    module = module or FakeModule(tmp_path / "work", tmp_path / "status")
    events = []
    engine = Engine({"agent": agent_flow.kind(module), "fake": lambda step, ctx: Outcome(DONE)},
                    progress=events.append)
    flow = load({"steps": steps, "inputs": {"goal": "目的"}}, "f", engine.kinds)
    store = Store(tmp_path / "state", display=lambda folder: f"runs/{folder.name}")   # 状態は作業空間の外
    agent.result_path = None
    original = store.create

    def create(*args, **kwargs):   # 実行の置き場所が決まったら、エージェントが書く結果のファイルの場所を覚える
        run = original(*args, **kwargs)
        agent.result_path = module.root / run.state["dir"] / "impl.json"   # 作業空間の ${run.dir}
        return run

    store.create = create
    return engine, flow, store, module, events


def test_agent_step_starts_waits_reads_the_result_and_stops(tmp_path, agent):
    agent.replies = {3: ("終わりました", {"ok": True, "message": "直しました", "score": 90})}
    engine, flow, store, module, events = setup(tmp_path, agent, [
        {"id": "impl", "type": "agent", "agent": "worker", "prompt": "${inputs.goal} を直す", "pass_if": "${out.score} >= 80"},
    ])
    run = engine.start(store, flow, {"goal": "0除算"}, run_id="r")
    step = run.steps["impl"]
    assert run.status == DONE and step["message"] == "直しました" and step["out"]["score"] == 90
    assert module.started[0][0] == "worker" and module.started[0][1].startswith("0除算 を直す")
    assert "runs/r/impl.json" in module.started[0][1]           # 結果の場所をプロンプトで渡す
    assert step["data"]["agent"] == "a-0000000001" and agent.stopped == ["a-0000000001"]
    assert any("エージェント：作業中（Edit）" in e for e in events)
    log = (run.folder / "impl.log").read_text(encoding="utf-8")
    assert "起動しました" in log and "止めました" in log


def test_without_a_result_file_the_last_reply_is_the_message(tmp_path, agent):
    agent.replies = {1: ("返答だけ", None)}
    engine, flow, store, _, _ = setup(tmp_path, agent, [{"id": "impl", "type": "agent", "agent": "w", "prompt": "p"}])
    run = engine.start(store, flow, run_id="r")
    assert run.status == DONE and run.steps["impl"]["message"] == "返答だけ" and run.steps["impl"]["out"] == {}


def test_ok_false_fails_and_on_fail_sends_the_feedback(tmp_path, agent):
    agent.replies = {1: ("", {"ok": False, "message": "テストが通らない"}), 2: ("", {"ok": True})}
    engine, flow, store, module, _ = setup(tmp_path, agent, [
        {"id": "impl", "type": "agent", "agent": "w", "prompt": "直す。${vars.feedback}",
         "on_fail": {"to": "impl", "max": 2}},
    ])
    run = engine.start(store, flow, run_id="r")
    assert run.status == DONE and run.steps["impl"]["backs"] == 1 and len(module.started) == 2
    assert module.started[1][1].startswith("直す。テストが通らない") and len(agent.stopped) == 2


def test_start_failure_is_a_failed_step(tmp_path, agent):
    error = EcoBuildError(ErrorCode.NOT_ON_TASK_BRANCH, "タスクブランチではありません。", hint="task start で")
    module = FakeModule(tmp_path / "work", tmp_path / "status", error=error)
    engine, flow, store, _, _ = setup(tmp_path, agent, [{"id": "impl", "type": "agent", "agent": "w", "prompt": "p"}],
                                      module)
    run = engine.start(store, flow, run_id="r")
    step = run.steps["impl"]
    assert run.status == FAILED and "タスクブランチではありません" in step["message"]
    assert step["out"]["error"]["code"] == "not_on_task_branch" and agent.stopped == []
    assert "ヒント：task start で" in (run.folder / "impl.log").read_text(encoding="utf-8")


def test_timeout_and_stopped_without_reply(tmp_path, agent, monkeypatch):
    engine, flow, store, _, _ = setup(tmp_path, agent, [
        {"id": "impl", "type": "agent", "agent": "w", "prompt": "p", "timeout": 0.05}])
    run = engine.start(store, flow, run_id="r")
    assert run.status == FAILED and "0 秒待っても" in run.steps["impl"]["message"] and agent.stopped
    monkeypatch.setattr(agent_flow, "STOPPED_GRACE", 0.0)
    stopped = FakeAgent(state=status.STOPPED, error="ログインが要ります")
    monkeypatch.setattr(status, "activity", lambda folder: stopped.activity(folder))
    engine, flow, store, _, _ = setup(tmp_path / "b", agent, [{"id": "impl", "type": "agent", "agent": "w", "prompt": "p"}])
    run = engine.start(store, flow, run_id="r")
    assert run.status == FAILED and run.steps["impl"]["message"] == "エージェントが返答せずに止まりました：ログインが要ります"


def test_resume_waits_for_the_same_agent(tmp_path, agent, monkeypatch):
    """待っている間に止めた（Ctrl+C）実行を続けると、新しく起動せず、同じエージェントを待ち直す。"""
    engine, flow, store, module, _ = setup(tmp_path, agent, [{"id": "impl", "type": "agent", "agent": "w", "prompt": "p"}])

    def interrupted(folder):
        raise KeyboardInterrupt

    monkeypatch.setattr(status, "activity", interrupted)
    with pytest.raises(KeyboardInterrupt):
        engine.start(store, flow, run_id="r")
    run = store.get("r")
    assert run.status == RUNNING and run.steps["impl"]["data"]["agent"] == "a-0000000001"
    agent.replies = {1: ("続きで終わり", None)}
    monkeypatch.setattr(status, "activity", lambda folder: agent.activity(folder))
    run = engine.resume(run)
    assert run.status == DONE and len(module.started) == 1 and run.steps["impl"]["message"] == "続きで終わり"


def test_a_stop_failure_only_notes_it(tmp_path, agent, monkeypatch):
    def refuse(agent_id, progress=None):
        raise EcoBuildError("agent_error", "動いていません。")

    monkeypatch.setattr(ecobuild_agent, "stop_agent", refuse)
    agent.replies = {1: ("済み", None)}
    engine, flow, store, _, events = setup(tmp_path, agent, [{"id": "impl", "type": "agent", "agent": "w", "prompt": "p"}])
    run = engine.start(store, flow, run_id="r")
    assert run.status == DONE and any("止められませんでした" in e for e in events)


def test_interrupted_while_starting_does_not_start_a_second_agent(tmp_path, agent, monkeypatch):
    """係に頼んでいる途中で止めても、記録の ID は残っている：続けると同じエージェントを待ち、取り消すと止める。"""
    module = FakeModule(tmp_path / "work", tmp_path / "status", interrupt=True)
    engine, flow, store, _, _ = setup(tmp_path, agent, [{"id": "impl", "type": "agent", "agent": "w", "prompt": "p"}],
                                      module)
    with pytest.raises(KeyboardInterrupt):
        engine.start(store, flow, run_id="r")
    assert store.get("r").steps["impl"]["data"]["agent"] == "a-0000000001"
    run = engine.cancel(store.get("r"))
    assert run.status == "cancelled" and agent.stopped == ["a-0000000001"] and len(module.started) == 1
    with pytest.raises(KeyboardInterrupt):
        engine.start(store, flow, run_id="r2")
    module.interrupt = False
    agent.replies = {1: ("済み", None)}
    run = engine.resume(store.get("r2"))
    assert run.status == DONE and len(module.started) == 2   # r2 で起動した1体だけ（2体目を起動しない）


def test_resume_counts_the_timeout_from_the_new_wait(tmp_path, agent, monkeypatch):
    engine, flow, store, module, _ = setup(tmp_path, agent, [
        {"id": "impl", "type": "agent", "agent": "w", "prompt": "p", "timeout": 5}])
    module.interrupt = True
    with pytest.raises(KeyboardInterrupt):
        engine.start(store, flow, run_id="r")
    run = store.get("r")
    run.steps["impl"]["data"]["started"] -= 3600   # 1時間前に起動した
    run.save()
    module.interrupt = False
    agent.replies = {2: ("済み", None)}
    assert engine.resume(store.get("r")).status == DONE


def test_agent_settings_are_checked():
    kinds = {"agent": agent_flow.kind(None)}
    _, problems = check({"steps": [
        {"id": "a", "type": "agent", "agent": "w"},
        {"id": "b", "type": "agent", "agent": 3, "prompt": "p"},
        {"id": "c", "type": "agent", "agent": "w", "prompt": "p", "model": "x"},
        {"id": "d", "type": "agent", "agent": "${steps.a.out.who}", "prompt": "p"},
        {"id": "e", "type": "agent", "agent": "${inputs.who}", "prompt": "${vars.feedback}"},
    ], "inputs": {"who": "登録"}}, "f", kinds)
    assert len(problems) == 4 and "agent（登録の名前）に展開してよいのは" in problems[3]
    assert len(problems) == 4 and "prompt がありません" in problems[0] and "agent は登録の名前" in problems[1]
