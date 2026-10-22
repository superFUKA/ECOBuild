"""アプリ用の起動（ecobuild_agent.app）：AI が起動した子は、係が claude -p の stream-json で持つ。

本物の Claude Code・コンテナの代わりに、偽の claude（FAKE：標準入力の発言を読み、決まった出来事を出す）で確かめる。
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from fakes import FakeGitHub
from ecobuild.errors import EcoBuildError
from ecobuild_agent import agents, app, children
from ecobuild_agent import inside
from ecobuild_agent import serve as agent_serve
from ecobuild_agent import status as agent_status
from ecobuild_agent.errors import ErrorCode
from ecobuild_bundle import Module
from ecobuild_cli import build_cli
from ecowork import WorkError

pytestmark = pytest.mark.local

# 偽の claude：受け取った発言を記録し（作業中でもすぐ）、1つずつ「道具を使う → 答える → 返答の終わり」の出来事を出す。
# 「ゆっくり」なら答える前に待ち、「落ちて」なら返答の途中で終わる。標準入力が閉じたら、残りを終えてから終わる。
FAKE = r'''
import io, json, os, queue, sys, threading, time
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
record, args = sys.argv[1], sys.argv[2:]
session = args[args.index("--session-id") + 1] if "--session-id" in args else args[args.index("--resume") + 1]
def out(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False) + "\n")
    sys.stdout.flush()
with open(record, "a", encoding="utf-8") as f:
    f.write(json.dumps({"args": args}, ensure_ascii=False) + "\n")
lines = queue.Queue()
def read():
    for line in sys.stdin:
        text = json.loads(line)["message"]["content"]
        with open(record, "a", encoding="utf-8") as f:
            f.write(json.dumps({"got": text}, ensure_ascii=False) + "\n")
        lines.put(text)
    lines.put(None)
threading.Thread(target=read, daemon=True).start()
out({"type": "system", "subtype": "init", "session_id": session, "model": "fake-model"})
while (text := lines.get()) is not None:
    out({"type": "user", "message": {"role": "user", "content": text}, "session_id": session})
    out({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ecobuild test"}}],
                                          "usage": {"input_tokens": 10, "cache_read_input_tokens": 90000}}})
    if "ゆっくり" in text:
        time.sleep(1.5)
    if "落ちて" in text:
        os._exit(3)   # sys.exit だと、stdin を読むスレッドが残って Linux では終わりに Python ごと落ちる（終了コードが変わる）
    out({"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {"five_hour": {"utilization": 0.25, "resetsAt": 1},
                                                                           "seven_day": {"utilization": 0.5, "resetsAt": 2}}}})
    out({"type": "assistant", "message": {"content": [{"type": "text", "text": "了解：" + text}]}})
    out({"type": "result", "subtype": "success", "is_error": False, "result": "了解：" + text, "session_id": session,
         "total_cost_usd": 0.01, "duration_ms": 1200, "num_turns": 2, "usage": {"input_tokens": 10, "output_tokens": 5},
         "modelUsage": {"fake-model": {"contextWindow": 1000000}},
         "permission_denials": [{"tool_name": "WebFetch"}] if "断られ" in text else []})
'''


@pytest.fixture
def lead(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    module.repository.create_task("大きな仕事").start(name="大きな仕事")
    return module


@pytest.fixture
def parent(lead):
    """lead の作業空間の、子を起動できるエージェント（管理役の登録）。"""
    task = lead.require_task_branch("x")
    record = agents.create(registration="manager", workspace=lead.root, task={"number": task.number, "branch": task.branch})
    agent_status.prepare(record.folder, lead.root)
    return record


class Fake:
    """偽の claude を起動する launch（係に渡す）と、その記録。"""

    def __init__(self, tmp_path: Path):
        self.script = tmp_path / "fake_claude.py"
        self.script.write_text(FAKE, encoding="utf-8")
        self.record = tmp_path / "record.jsonl"
        self.launched = []

    def __call__(self, agent_id, resume, progress):
        record = agents.load(agent_id)
        session = resume or f"s-{len(self.launched) + 1}"
        self.launched.append({"root": record.root, "id": agent_id, "resume": resume})
        agents.update(agent_id, session=session)   # app_launch と同じく、会話を記録に書く
        folder = agent_status.prepare(record.folder, record.root)
        argv = (sys.executable, str(self.script), str(self.record),
                *(("--resume", resume) if resume else ("--session-id", session)))
        return app.Launch(record.root, folder, argv, None, session, agent_id, record.registration)

    def got(self) -> list[str]:
        if not self.record.is_file():
            return []
        return [x["got"] for x in map(json.loads, self.record.read_text(encoding="utf-8").splitlines()) if "got" in x]


def until(check, serve=None, seconds=15.0):
    """check() が真になるまで（serve があれば見回りながら）待つ。"""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if serve is not None:
            serve.step()
        if check():
            return
        time.sleep(0.05)
    pytest.fail("待ちきれませんでした")


def tool(serve, caller, name, **arguments):
    """caller の置き場所からのツールの頼み（requests/ に書き、係が拾って実行する）。"""
    requests = caller.folder / children.REQUESTS
    requests.mkdir(exist_ok=True)
    key = f"t{time.monotonic_ns()}"
    (requests / f"{key}.json").write_text(json.dumps({"id": key, "tool": name, "arguments": arguments,
                                                      "agent": caller.id}), encoding="utf-8")
    serve.step()
    serve.wait()
    return json.loads((requests / f"{key}.result.json").read_text(encoding="utf-8"))


def human(serve, record, *args):
    """人の操作（agent <操作> <ID> …）を係に頼む。"""
    return serve.handle(record.root, {"id": "h", "args": ["agent", *args], "cwd": "."})


def state(record) -> dict:
    return agent_status.read(record.folder / agent_status.STATE) or {}


def helper(lead, parent) -> agents.AgentRecord:
    return agents.create(registration="worker", workspace=lead.root, kind=agents.HELPER, parent=parent.id,
                         task=parent.task, name="画面")


def test_the_serve_runs_a_child_without_a_screen_from_start_to_close(lead, parent, tmp_path):
    """起動（children_start）→ 係がアプリ用で起動 → 最初の仕事が標準入力に → 出来事が events.jsonl・state.json に →
    返答の終わりで親に知らせ → 作業中の言付けがすぐ標準入力に → 閉じるのは作業中でなくなってから。"""
    fake = Fake(tmp_path)
    ran = []
    emitted = []
    serve = agent_serve.Serve(lambda args, cwd, **kw: (ran.append(args), {"ok": True, "result": {}})[1],
                              emit=emitted.append, launch=fake)
    doc = tool(serve, parent, "children_start", registration="worker", kind="helper", brief="目的：画面を作る",
               title="画面")
    assert doc["ok"] and doc["result"]["app"], doc
    child = agents.load(doc["result"]["id"])
    assert fake.launched[0]["root"] == lead.root and fake.launched[0]["id"] == child.id
    until(lambda: len(fake.got()) == 1 and fake.got()[0].endswith("目的：画面を作る"))     # 最初の仕事は標準入力から
    until(lambda: state(child).get("replied_at"), serve)
    found = state(child)
    assert found["session"] == "s-1" and found["model"] == "fake-model" and found["state"] == agent_status.IDLE
    assert found["last_reply"].endswith("目的：画面を作る") and found["usage"]["cost_usd"] == 0.01
    assert found["limits"]["five_hour"]["used_percentage"] == 25.0 and found["context"] == 9.0
    events, _ = app.read_events(child.folder)
    assert [e["type"] for e in events][:3] == ["ecobuild", "system", "user"] and events[-1]["type"] == "result"

    until(lambda: list((parent.folder / agent_status.INBOX).glob("*.json")), serve)
    serve.wait()
    notice = agent_status.take(parent.folder)
    assert notice and f"子「画面」（{child.id}・手伝い" in notice["text"] and notice["text"].endswith("目的：画面を作る")
    assert ["project", "update"] in ran

    assert tool(serve, parent, "children_send", id=child.id, text="ゆっくり確かめて")["ok"]   # 作業中に2つ
    until(lambda: len(fake.got()) == 2, serve)
    until(lambda: state(child).get("state") == agent_status.WORKING, serve)
    assert state(child)["doing"] == "Bash：ecobuild test"
    seen = tool(serve, parent, "children_list")["result"]["members"][0]
    assert seen["mode"] == agent_status.APP and seen["state"] == agent_status.WORKING
    assert "今：Bash：ecobuild test" in children.describe_activity(seen)
    tool(serve, parent, "children_send", id=child.id, text="ボタンは右に")
    until(lambda: len(fake.got()) == 3, serve, seconds=1.2)                             # 作業中でもすぐ入る
    assert state(child)["state"] == agent_status.WORKING

    refused = tool(serve, parent, "children_close", id=child.id)
    assert not refused["ok"] and serve.apps.holds(child.id)                             # 作業中は閉じない（止めない）
    assert refused["error"]["details"] == ["「画面」は作業中です"]
    doc = human(serve, child, "close", child.id, "--force")                            # 人は作業中でも閉じられる
    assert doc["ok"] and not serve.apps.holds(child.id)                                 # 返答を終えてから止めた
    assert fake.got()[-1].endswith("ボタンは右に") and agent_status.directory(child.id) is None   # 記録・置き場所も消す
    assert not emitted and child.id not in [a.id for a in agents.all_records()]
    assert json.loads((Path(os.environ["ECOBUILD_HOME"]) / app.HELD).read_text(encoding="utf-8")) == {"agents": []}


def test_restarting_stops_and_starts_again_without_a_screen(lead, parent, tmp_path):
    fake = Fake(tmp_path)
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    started = tool(serve, parent, "children_start", registration="worker", kind="helper", brief="仕事")
    child = agents.load(started["result"]["id"])
    until(lambda: state(child).get("replied_at"), serve)
    doc = tool(serve, parent, "children_restart", id=child.id, resume=True)
    assert doc["ok"] and doc["result"]["app"] and doc["result"]["resumed"]
    assert fake.launched[1] == {"root": lead.root, "id": child.id, "resume": "s-1"}       # 前の会話の続きから
    until(lambda: fake.got()[-1:] == [children.RESUME_PROMPT])
    assert agent_status.session_of(child.folder) == "s-1"
    doc = human(serve, child, "restart", child.id)                                     # 人も起動し直せる（新しい会話）
    assert doc["ok"] and not doc["result"]["resumed"] and fake.launched[2]["resume"] == ""
    serve.apps.stop(child.id)


def test_an_agent_that_ends_in_the_middle_is_reported_to_the_parent(lead, parent, tmp_path):
    """子がどんな状態で返答を終えても（途中で落ちても）、親に知らせる。"""
    child = helper(lead, parent)
    fake = Fake(tmp_path)
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    serve.apps.start(child.id, prompt="落ちてください")
    until(lambda: not serve.apps.holds(child.id), serve)
    serve.step()
    serve.wait()
    notice = agent_status.take(parent.folder)
    assert notice and "返答の途中で終わりました：終了コード 3" in notice["text"]
    assert state(child)["state"] == agent_status.STOPPED and "終了コード 3" in state(child)["error"]


def test_stopping_the_serve_lets_the_reply_finish_and_the_next_serve_resumes(lead, parent, tmp_path):
    """係が終わるときは入力を閉じるだけ（返答の途中のものは返答を終えて終わる）。次の係は引き継いで出来事を読み
    （終わった返答も親に知らせる）、終わったら --resume で起こし、親に知らせる。"""
    child = helper(lead, parent)
    fake = Fake(tmp_path)
    first = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    agent = first.apps.start(child.id, prompt="ゆっくりやって")
    until(lambda: state(child).get("state") == agent_status.WORKING, first)
    first.apps.close(wait=0.1)                                                           # 返答の途中で係が終わる
    assert agent.alive()                                                                 # 止めない
    threading.Thread(target=agent.process.wait, daemon=True).start()                    # 前の係のプロセスは終わったもの
    held = json.loads((Path(os.environ["ECOBUILD_HOME"]) / app.HELD).read_text(encoding="utf-8"))["agents"]
    assert [x["id"] for x in held] == [child.id] and held[0]["session"] == "s-1"

    second = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    second.wake()
    assert second.apps.get(child.id) is not None and len(fake.launched) == 1              # 終わるまでは起こさない
    until(lambda: len(fake.launched) == 2, second)
    second.wait()
    assert fake.launched[1]["resume"] == "s-1"
    texts = []

    def collect():
        while (item := agent_status.take(parent.folder)) is not None:
            texts.append(item["text"])
        return len(texts) >= 2
    until(collect, second)
    assert any(t.endswith("了解：ゆっくりやって") for t in texts)                          # 係がいない間に終えた返答
    assert any("係が起動し直したので、子「画面」" in t and "前の会話の続きから起こしました" in t for t in texts)
    assert second.apps.holds(child.id) and agent.process.poll() == 0
    assert fake.got() == ["ゆっくりやって"]                                                # 途中ではなかったので何も入れない
    second.apps.stop(child.id)


def test_the_next_serve_does_not_wake_a_child_whose_task_is_closed(lead, parent, tmp_path):
    """タスクが閉じた子（閉じ忘れたもの）は、次の係が起こさない：持つのをやめ、親に知らせる。"""
    child = helper(lead, parent)
    fake = Fake(tmp_path)
    first = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    agent = first.apps.start(child.id, prompt="はじめて")
    until(lambda: state(child).get("replied_at"), first)
    first.apps.close(wait=0.1)
    threading.Thread(target=agent.process.wait, daemon=True).start()

    asked = []

    def run(args, cwd, **_):
        asked.append((args, Path(cwd)))
        return {"ok": True, "result": {"state": "closed"}} if args[:2] == ["task", "status"] else {"ok": True, "result": {}}
    second = agent_serve.Serve(run, launch=fake)
    second.wake()
    until(lambda: not second.apps.holds(child.id), second)
    second.wait()
    assert len(fake.launched) == 1 and (["task", "status", "--json"], lead.root) in asked   # 起こさない
    assert json.loads((Path(os.environ["ECOBUILD_HOME"]) / app.HELD).read_text(encoding="utf-8")) == {"agents": []}
    texts = []

    def collect():
        while (item := agent_status.take(parent.folder)) is not None:
            texts.append(item["text"])
        return any("起こしませんでした" in t for t in texts)
    until(collect, second)
    assert any("タスクが閉じています" in t for t in texts)


def test_people_can_take_over_and_hand_back(lead, parent, tmp_path):
    """引き取る：係が止めて会話を返す（人は対話型で claude --resume）。返す：対話型を閉じた後、係が続きから起こす。
    起動した側（GUI）がいれば、人の画面で開くよう出来事（agent-start）で頼む。"""
    child = helper(lead, parent)
    fake = Fake(tmp_path)
    emitted = []
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake, emit=emitted.append)
    serve.apps.start(child.id, prompt="はじめて")
    until(lambda: state(child).get("replied_at"), serve)
    resume = Module.find(lead.root).start_agent
    assert code_of(lambda: resume(program="claude --resume s-1")) == ErrorCode.AGENT_ERROR   # 同じ会話を同時に対話型で動かさない

    doc = human(serve, child, "takeover", child.id)
    assert doc["ok"] and doc["result"]["agent"] == "claude --resume s-1" and not serve.apps.holds(child.id)
    assert doc["result"]["opened"] and emitted[-1]["event"] == "agent-start" and emitted[-1]["id"] == child.id
    assert emitted[-1]["program"] == "claude --resume s-1" and emitted[-1]["parent"] == parent.id
    assert emitted[-1]["kind"] == agents.HELPER and emitted[-1]["registration"] == "worker"
    agent_status.started(child.folder, os.getpid())                                    # 人の画面で動いている
    doc = human(serve, child, "handback", child.id)
    assert not doc["ok"] and "まだ対話型" in doc["error"]["message"]
    agent_status.ended(child.folder, os.getpid())                                      # 閉じた
    doc = human(serve, child, "handback", child.id)
    assert doc["ok"] and doc["result"]["app"] and fake.launched[-1]["resume"] == "s-1"
    until(lambda: fake.got()[-1:] == [app.HANDBACK_PROMPT])
    serve.apps.stop(child.id)


def test_people_can_start_and_stop_their_own_agent_without_a_screen(lead, tmp_path):
    """係は記録のあるエージェントを ID で起動・停止する（同じ作業空間に何人でも。同じ ID は2重にしない）。"""
    fake = Fake(tmp_path)
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    one = agents.create(registration="lead", workspace=lead.root)
    two = agents.create(registration="worker", workspace=lead.root, parent=one.id, kind=agents.HELPER)
    doc = serve.handle(lead.root, {"id": "s", "args": ["agent", "start", "--app", "--id", one.id, "--prompt", "計画して"],
                                   "cwd": "."})
    assert doc["ok"] and doc["result"]["id"] == one.id and doc["result"]["registration"] == "lead"
    assert fake.launched[0]["root"] == lead.root
    until(lambda: fake.got() == ["計画して"])
    again = serve.handle(lead.root, {"id": "x", "args": ["agent", "start", "--app", "--id", one.id], "cwd": "."})
    assert not again["ok"]                                                                 # 同じエージェントは2重にしない
    assert serve.handle(lead.root, {"id": "w", "args": ["agent", "start", "--app", "--id", two.id], "cwd": "."})["ok"]
    assert serve.apps.holds(one.id) and serve.apps.holds(two.id)                         # 同じ作業空間に2人
    assert two.folder != one.folder and two.folder.parent == one.folder.parent           # 置き場所は ID ごと
    assert not serve.handle(lead.root, {"id": "y", "args": ["agent", "start"], "cwd": "."})["ok"]   # 新しい画面は係でない
    assert not serve.handle(lead.root, {"id": "t", "args": ["agent", "team", "list"], "cwd": "."})["ok"]   # 前の版の頼み
    assert serve.handle(lead.root, {"id": "z", "args": ["agent", "stop", one.id], "cwd": "."})["ok"]
    assert not serve.apps.holds(one.id) and serve.apps.holds(two.id)
    held = json.loads((Path(os.environ["ECOBUILD_HOME"]) / app.HELD).read_text(encoding="utf-8"))["agents"]
    assert held == [{"id": two.id, "workspace": str(lead.root), "session": "s-2", "registration": "worker"}]
    serve.apps.stop(two.id)


def test_people_start_status_and_stop_their_own_agent_with_the_cli(lead, tmp_path, monkeypatch):
    """CLI：agent start --as <登録> --app は記録を作って係に頼み、agent status・agent log で様子を見て、agent stop <ID> で止める。"""
    fake = Fake(tmp_path)
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    stop = threading.Event()
    threading.Thread(target=agent_serve.serve_forever, args=(serve, stop, 0.1), daemon=True).start()
    monkeypatch.chdir(lead.root)
    from ecobuild import config
    config.save_local(lead.root, {"container": True})
    runner = CliRunner()
    invoke = lambda *args: json.loads(runner.invoke(build_cli(), [*args, "--json"], catch_exceptions=False).stdout)
    try:
        started = invoke("agent", "start", "--as", "lead", "--app", "--prompt", "進めて")
        assert started["ok"], started
        agent_id = started["result"]["id"]
        assert started["result"]["registration"] == "lead" and Path(started["result"]["workspace"]) == lead.root
        until(lambda: (agent_status.read(agents.load(agent_id).folder / agent_status.STATE) or {}).get("replied_at"))
        shown = invoke("agent", "status")["result"]
        assert [a["id"] for a in shown["agents"]] == [agent_id]
        one = invoke("agent", "status", agent_id)["result"]
        assert one["mode"] == agent_status.APP and one["last_reply"] == "了解：進めて" and one["session"] == "s-1"
        own = invoke("agent", "log")["result"]
        assert any(e.get("result") == "了解：進めて" for e in own["events"])
        assert invoke("agent", "stop", agent_id)["ok"] and not serve.apps.holds(agent_id)
        assert invoke("agent", "stop", agent_id)["error"]["code"] == "agent_error"        # もう動いていない
    finally:
        stop.set()
        for agent in serve.apps.agents():
            serve.apps.stop(agent.agent_id, 5)


def test_the_cli_reads_the_log_lists_and_asks_the_serve(lead, parent, tmp_path, monkeypatch):
    """CLI：agent log <ID>（--json・--after）・agent list・agent send、agent takeover・handback・restart・close は係に頼む。"""
    child = helper(lead, parent)
    fake = Fake(tmp_path)
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    stop = threading.Event()
    threading.Thread(target=agent_serve.serve_forever, args=(serve, stop, 0.1), daemon=True).start()
    monkeypatch.chdir(lead.root)
    runner = CliRunner()
    invoke = lambda *args: json.loads(runner.invoke(build_cli(), [*args, "--json"], catch_exceptions=False).stdout)
    try:
        serve.apps.start(child.id, prompt="はじめて")
        until(lambda: state(child).get("replied_at"))
        log = invoke("agent", "log", child.id)
        assert log["ok"] and log["result"]["events"][-1]["type"] == "result" and log["result"]["id"] == child.id
        assert log["result"]["activity"]["mode"] == agent_status.APP
        later = invoke("agent", "log", child.id, "--after", str(log["result"]["next"]))
        assert later["result"]["events"] == [] and later["result"]["next"] == log["result"]["next"]
        human_log = runner.invoke(build_cli(), ["agent", "log", child.id], catch_exceptions=False).stdout
        assert "▶ 入力：はじめて" in human_log and "・Bash：ecobuild test" in human_log and "■ 返答の終わり" in human_log
        everyone = invoke("agent", "list")["result"]
        assert [(a["id"], a["parent"]) for a in everyone] == [(parent.id, None), (child.id, parent.id)]
        tree = runner.invoke(build_cli(), ["agent", "list"], catch_exceptions=False).stdout
        assert f"「画面」（{child.id}・worker・手伝い" in tree and tree.index(parent.id) < tree.index(child.id)
        sent = invoke("agent", "send", child.id, "右に", "寄せて")
        assert sent["ok"] and sent["result"]["message_id"]
        until(lambda: fake.got()[-1:] == ["[人から] 右に 寄せて"])

        taken = invoke("agent", "takeover", child.id, "--no-open")
        assert taken["ok"] and taken["result"]["agent"] == "claude --resume s-1"
        given = invoke("agent", "handback", child.id)
        assert given["ok"] and given["result"]["app"]
        until(lambda: fake.got()[-1:] == [app.HANDBACK_PROMPT])
        until(lambda: state(child).get("state") == agent_status.IDLE)
        restarted = invoke("agent", "restart", child.id, "--resume")
        assert restarted["ok"] and restarted["result"]["resumed"]
        until(lambda: state(child).get("state") == agent_status.IDLE and fake.got()[-1:] == [children.RESUME_PROMPT])
        closed = invoke("agent", "close", child.id, "--force")
        assert closed["ok"] and child.id not in [a["id"] for a in invoke("agent", "list")["result"]]
        assert agent_status.directory(child.id) is None                                  # 頼みの置き場所も残さない
    finally:
        stop.set()
        for agent in serve.apps.agents():
            serve.apps.stop(agent.agent_id, 5)


def test_the_children_have_the_nested_children_and_recent_lines(lead, parent, monkeypatch):
    """agent children <ID>：子と、その子を members に入れ子で。--recent N：1人ごとに最新の出来事の人向けの行（GUI の
    一覧・格子）。出来事のファイルは終わりだけを読む（途中から読んだ欠けた行は捨てる）。"""
    sub = agents.create(registration="manager", workspace=lead.root, parent=parent.id, kind=agents.HELPER, name="下の管理役")
    worker = agents.create(registration="worker", workspace=lead.root, parent=sub.id, kind=agents.HELPER, name="画面")
    folder = agent_status.prepare(worker.folder, lead.root)
    lines = [{"type": "user", "message": {"content": "はじめて"}},
             {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ecobuild test"}}]}},
             {"type": "rate_limit_event"},
             {"type": "assistant", "message": {"content": [{"type": "text", "text": "できました"}]}}]
    (folder / app.EVENTS).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines) + '{"type": "us',
                                     encoding="utf-8")
    assert [e["type"] for e in app.recent_events(folder)] == ["user", "assistant", "rate_limit_event", "assistant"]
    assert [e["type"] for e in app.recent_events(folder, size=150)] == ["rate_limit_event", "assistant"]

    monkeypatch.chdir(lead.root)
    invoke = lambda *args: json.loads(CliRunner().invoke(build_cli(), [*args, "--json"], catch_exceptions=False).stdout)
    plain = invoke("agent", "children", parent.id)["result"]["members"]
    assert [m["name"] for m in plain] == ["下の管理役"] and "recent" not in plain[0]
    assert [m["name"] for m in plain[0]["members"]] == ["画面"]
    assert {"id", "kind", "registration", "state", "messages", "submission"} <= set(plain[0])
    nested = invoke("agent", "children", parent.id, "--recent", "2")["result"]["members"]
    assert nested[0]["recent"] == [] and nested[0]["members"][0]["recent"] == ["  ・Bash：ecobuild test", "◀ できました"]
    human = CliRunner().invoke(build_cli(), ["agent", "children", parent.id], catch_exceptions=False).stdout
    assert "「下の管理役」" in human and "\n    「画面」" in human


def test_the_launch_is_made_like_the_interactive_one(lead, monkeypatch):
    """起動のしかた（AgentModule.app_launch）：コンテナの中の claude -p の stream-json。会話の ID・モデル・使い方の文・
    MCP は対話型と同じ作り方（登録から）。statusLine・返答の終わりのフックは付けず、シェルの関所だけを付ける。"""
    from ecobuild import config
    config.save_local(lead.root, {"container": True})
    seen = {}

    def launch(root, agent, **options):
        seen.update(agent=agent, **options)
        return ["docker", "exec", "--interactive", *agent], {"X": "1"}
    monkeypatch.setattr(inside, "agent_launch", launch)
    record = agents.create(registration="manager", workspace=lead.root, model="opus",
                           task={"number": 1, "branch": "task/1-大きな仕事"})
    found = lead.app_launch(record.id)
    command = seen["agent"]
    assert command[:8] == ("claude", *app.FLAGS) and seen["stdin"] and not seen["tty"] and seen["tag"]
    assert seen["agent_id"] == record.id and found.agent_id == record.id and found.registration == "manager"
    assert command[command.index("--session-id") + 1] == found.session == agents.load(record.id).session
    assert command[command.index("--model") + 1] == "opus"
    where = f"{agent_status.INSIDE}/{record.id}"
    assert command[command.index("--append-system-prompt-file") + 1] == f"{where}/guide.md"
    assert command[command.index("--mcp-config") + 1] == f"{where}/mcp.json" and "--strict-mcp-config" in command
    assert found.folder == record.folder
    settings = json.loads((found.folder / agent_status.SETTINGS).read_text(encoding="utf-8"))
    assert "statusLine" not in settings and list(settings["hooks"]) == ["PreToolUse"]
    assert settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "ecobuild agent guard"
    assert "## あなたの役：管理役" in (found.folder / "guide.md").read_text(encoding="utf-8")
    again = lead.app_launch(record.id, resume=found.session)
    assert "--session-id" not in seen["agent"] and seen["agent"][seen["agent"].index("--resume") + 1] == found.session
    assert again.agent_id == record.id                                                    # 同じエージェントの続き


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def test_a_second_agent_gets_its_own_folder_while_one_is_alive(lead, monkeypatch):
    """同じ作業空間に2人目を起動できる。置き場所・受け箱・guide.md・mcp.json は混ざらない。同じエージェント（ID）は
    2重に起動しない（死んだ pid なら止めない）。"""
    import subprocess
    import ecoagent
    started = []
    monkeypatch.setattr(ecoagent, "start", lambda directory, command, **_: started.append(tuple(command))
                        or ecoagent.Session(os.getpid(), tuple(command), directory))
    monkeypatch.setattr(inside, "agent_launch", lambda root, agent, **_: (tuple(agent), None))
    first = lead.start_agent("lead")
    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        agent_status.started(first.folder, live.pid)                                   # 1人目が動いている
        second = lead.start_agent("manager", parent=first.id, kind=agents.HELPER, prompt="手伝って")
        assert second.id != first.id and second.folder != first.folder and second.parent == first.id
        assert started[-1][:2] == ("claude", "手伝って")
        for record in (first, second):
            assert record.id in (record.folder / "guide.md").read_text(encoding="utf-8")
            server = json.loads((record.folder / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["ecobuild"]
            assert server["args"][3] == record.id and server["args"][7] == record.kind
        assert "手伝いです" in (second.folder / "guide.md").read_text(encoding="utf-8")
        agent_status.put(second.folder, "手伝いへ")
        assert agent_status.take(first.folder) is None and agent_status.take(second.folder)["text"] == "手伝いへ"
        with pytest.raises(EcoBuildError) as stopped:
            lead._no_other_agent(agents.load(first.id), wait=0)
        assert stopped.value.code == ErrorCode.AGENT_ERROR and str(live.pid) in str(stopped.value)
        resume = f"claude --resume {agents.load(first.id).session}"
        assert code_of(lambda: lead.start_agent(program=resume)) == ErrorCode.AGENT_ERROR   # 同じ ID は2重にしない
        assert code_of(lambda: lead.app_launch(first.id)) == ErrorCode.AGENT_ERROR
    finally:
        live.kill()
        live.wait()
    lead._no_other_agent(agents.load(first.id), wait=0)   # 終わった pid では止めない（起動し直しの後）
    assert lead.start_agent(program=resume).id == first.id
