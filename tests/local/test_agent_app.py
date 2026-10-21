"""アプリ用の起動（ecobuild_agent.app）：AI が起動した作業役は、係が claude -p の stream-json で持つ。

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
import ecobuild_container as container
from ecobuild.errors import EcoBuildError
from ecobuild_agent import app
from ecobuild_agent import inside
from ecobuild_agent import serve as agent_serve
from ecobuild_agent import status as agent_status
from ecobuild_agent import team
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
    (module.root / team.MEMBER_FILE).parent.mkdir(parents=True, exist_ok=True)
    (module.root / team.MEMBER_FILE).write_text(json.dumps({"role": team.MANAGER}), encoding="utf-8")   # 作業役を作れる役
    return module


class Fake:
    """偽の claude を起動する launch（係に渡す）と、その記録。"""

    def __init__(self, tmp_path: Path):
        self.script = tmp_path / "fake_claude.py"
        self.script.write_text(FAKE, encoding="utf-8")
        self.record = tmp_path / "record.jsonl"
        self.launched = []

    def __call__(self, root, role, resume, progress):
        root = Path(root)
        session = resume or f"s-{len(self.launched) + 1}"
        self.launched.append({"root": root, "role": role, "resume": resume})
        folder = agent_status.prepare(container.name(root), root)
        argv = (sys.executable, str(self.script), str(self.record),
                *(("--resume", resume) if resume else ("--session-id", session)))
        return app.Launch(root, folder, argv, None, session, role or team.role_of(root))

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


def request(serve, folder, key, args, cwd="."):
    requests = folder / team.REQUESTS
    requests.mkdir(exist_ok=True)
    (requests / f"{key}.json").write_text(json.dumps({"id": key, "args": args, "cwd": cwd}), encoding="utf-8")
    serve.step()
    serve.wait()
    return json.loads((requests / f"{key}.result.json").read_text(encoding="utf-8"))


def made(member):
    def run(args, cwd, **_):
        if args[:3] in (["agent", "team", "start"], ["agent", "team", "restart"]):
            resume = "--resume" in args
            return {"ok": True, "result": {"path": str(member.path), "name": member.name, "role": "worker",
                                           "prompt": team.RESUME_PROMPT if resume else "仕事を読んで",
                                           **({"agent": "claude --resume s-1"} if resume else {})}}
        return {"ok": True, "result": {}}
    return run


def state(path) -> dict:
    return agent_status.read(team.inbox_of(path) / agent_status.STATE) or {}


def test_the_serve_runs_a_worker_without_a_screen_from_start_to_close(lead, tmp_path):
    """作成 → 係がアプリ用で起動 → 最初の仕事が標準入力に → 出来事が events.jsonl・state.json に → 返答の終わりで進行役に
    知らせ → 作業中の send がすぐ標準入力に → close で止まる。"""
    member = team.create(lead, "画面", "目的：画面を作る")
    folder = agent_status.prepare(container.name(lead.root), lead.root)
    fake = Fake(tmp_path)
    ran = []
    run = made(member)
    emitted = []
    serve = agent_serve.Serve(lambda args, cwd, **kw: (ran.append(args), run(args, cwd))[1], emit=emitted.append,
                              launch=fake)

    doc = request(serve, folder, "a", ["agent", "team", "start", "画面", "--json"])
    assert doc["ok"] and doc["result"]["app"] and fake.launched[0]["root"] == member.path
    until(lambda: fake.got() == ["仕事を読んで"])                                         # 最初の仕事は標準入力から
    until(lambda: state(member.path).get("replied_at"), serve)
    found = state(member.path)
    assert found["session"] == "s-1" and found["model"] == "fake-model" and found["state"] == agent_status.IDLE
    assert found["last_reply"] == "了解：仕事を読んで" and found["usage"]["cost_usd"] == 0.01
    assert found["limits"]["five_hour"]["used_percentage"] == 25.0 and found["context"] == 9.0
    events, _ = app.read_events(team.inbox_of(member.path))
    assert [e["type"] for e in events][:3] == ["ecobuild", "system", "user"] and events[-1]["type"] == "result"

    until(lambda: list((folder / agent_status.INBOX).glob("*.json")), serve)
    serve.wait()
    notice = agent_status.take(folder)
    assert notice and "作業役「画面」" in notice["text"] and notice["text"].endswith("了解：仕事を読んで")   # 進行役に知らせ
    assert ["project", "update"] in ran

    team.send(lead.root, "画面", "ゆっくり確かめて")                                      # 作業中に2つ
    until(lambda: len(fake.got()) == 2, serve)
    until(lambda: state(member.path).get("state") == agent_status.WORKING, serve)
    assert state(member.path)["doing"] == "Bash：ecobuild test"
    seen = team.find(lead.root, "画面")
    assert seen.mode == agent_status.APP and seen.state == agent_status.WORKING and seen.doing == "Bash：ecobuild test"
    assert "今：Bash：ecobuild test" in team.describe_activity(seen.__dict__)
    team.send(lead.root, "画面", "ボタンは右に")
    until(lambda: len(fake.got()) == 3, serve, seconds=1.2)                             # 作業中でもすぐ入る
    assert state(member.path)["state"] == agent_status.WORKING

    refused = request(serve, folder, "w", ["agent", "team", "close", "画面"])
    assert not refused["ok"] and serve.apps.holds(member.path)                          # 作業中は閉じない（止めない）
    assert refused["error"]["details"] == ["「画面」は作業中です"]
    doc = request(serve, folder, "c", ["agent", "team", "close", "画面", "--force"])
    assert doc["ok"] and not serve.apps.holds(member.path)                              # 返答を終えてから止めた
    assert state(member.path)["state"] == agent_status.STOPPED
    assert state(member.path)["last_reply"] .endswith("から] ボタンは右に")   # 途中で切っていない
    assert ran[-1][:3] == ["agent", "team", "close"] and not emitted                   # タブは開かせない・止めさせない
    assert agent_status.activity(team.inbox_of(member.path))["state"] == agent_status.STOPPED
    assert json.loads((Path(os.environ["ECOBUILD_HOME"]) / app.HELD).read_text(encoding="utf-8")) == {"agents": []}


def test_restarting_stops_and_starts_again_without_a_screen(lead, tmp_path):
    member = team.create(lead, "画面", "目的：画面を作る")
    folder = agent_status.prepare(container.name(lead.root), lead.root)
    fake = Fake(tmp_path)
    serve = agent_serve.Serve(made(member), launch=fake)
    request(serve, folder, "a", ["agent", "team", "start", "画面"])
    until(lambda: state(member.path).get("replied_at"), serve)
    doc = request(serve, folder, "r", ["agent", "team", "restart", "画面", "--resume"])
    assert doc["ok"] and doc["result"]["app"]
    assert fake.launched[1] == {"root": member.path, "role": "worker", "resume": "s-1"}   # 前の会話の続きから
    until(lambda: fake.got()[-1:] == [team.RESUME_PROMPT])
    assert agent_status.session_of(team.inbox_of(member.path)) == "s-1"
    serve.apps.stop(member.path)


def test_an_agent_that_ends_in_the_middle_is_reported_to_the_lead(lead, tmp_path):
    """作業役がどんな状態で返答を終えても（途中で落ちても）、進行役に知らせる。"""
    member = team.create(lead, "画面", "目的：画面を作る")
    folder = agent_status.prepare(container.name(lead.root), lead.root)
    fake = Fake(tmp_path)
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    serve.apps.start(member.path, role="worker", prompt="落ちてください")
    until(lambda: not serve.apps.holds(member.path), serve)
    serve.step()
    serve.wait()
    notice = agent_status.take(folder)
    assert notice and "返答の途中で終わりました：終了コード 3" in notice["text"]
    assert state(member.path)["state"] == agent_status.STOPPED and "終了コード 3" in state(member.path)["error"]


def test_stopping_the_serve_lets_the_reply_finish_and_the_next_serve_resumes(lead, tmp_path):
    """係が終わるときは入力を閉じるだけ（返答の途中のものは返答を終えて終わる）。次の係は引き継いで出来事を読み
    （終わった返答も進行役に知らせる）、終わったら --resume で起こし、進行役に知らせる。"""
    member = team.create(lead, "画面", "目的：画面を作る")
    folder = agent_status.prepare(container.name(lead.root), lead.root)
    fake = Fake(tmp_path)
    first = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    agent = first.apps.start(member.path, role="worker", prompt="ゆっくりやって")
    until(lambda: state(member.path).get("state") == agent_status.WORKING, first)
    first.apps.close(wait=0.1)                                                           # 返答の途中で係が終わる
    assert agent.alive()                                                                 # 止めない
    threading.Thread(target=agent.process.wait, daemon=True).start()                    # 前の係のプロセスは終わったもの
    held = json.loads((Path(os.environ["ECOBUILD_HOME"]) / app.HELD).read_text(encoding="utf-8"))["agents"]
    assert [Path(x["root"]) for x in held] == [member.path] and held[0]["session"] == "s-1"

    second = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    second.wake()
    assert second.apps.get(member.path) is not None and len(fake.launched) == 1          # 終わるまでは起こさない
    until(lambda: len(fake.launched) == 2, second)
    second.wait()
    assert fake.launched[1]["resume"] == "s-1"
    texts = []

    def collect():
        while (item := agent_status.take(folder)) is not None:
            texts.append(item["text"])
        return len(texts) >= 2
    until(collect, second)
    assert any(t.endswith("了解：ゆっくりやって") for t in texts)                          # 係がいない間に終えた返答
    assert any("係が起動し直したので、作業役「画面」を前の会話の続きから起こしました" in t for t in texts)
    assert second.apps.holds(member.path) and agent.process.poll() == 0
    assert fake.got() == ["ゆっくりやって"]                                                # 途中ではなかったので何も入れない
    second.apps.stop(member.path)


def test_people_can_take_over_and_hand_back(lead, tmp_path):
    """引き取る：係が止めて会話を返す（人は対話型で claude --resume）。返す：対話型を閉じた後、係が続きから起こす。"""
    member = team.create(lead, "画面", "目的：画面を作る")
    fake = Fake(tmp_path)
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    serve.apps.start(member.path, role="worker", prompt="はじめて")
    until(lambda: state(member.path).get("replied_at"), serve)
    member_folder = team.inbox_of(member.path)
    assert code_of(lambda: Module.find(member.path).start_agent(("claude",))) == ErrorCode.AGENT_ERROR   # 同時に対話型は動かさない

    doc = serve.handle(lead.root, {"id": "t", "args": ["agent", "team", "takeover", "画面"], "cwd": "."})
    assert doc["ok"] and doc["result"]["agent"] == "claude --resume s-1" and not serve.apps.holds(member.path)
    agent_status.started(member_folder, os.getpid())                                    # 人の画面で動いている
    doc = serve.handle(lead.root, {"id": "h", "args": ["agent", "team", "handback", "画面"], "cwd": "."})
    assert not doc["ok"] and "まだ対話型" in doc["error"]["message"]
    agent_status.ended(member_folder, os.getpid())                                      # 閉じた
    doc = serve.handle(lead.root, {"id": "h", "args": ["agent", "team", "handback", "画面"], "cwd": "."})
    assert doc["ok"] and doc["result"]["app"] and fake.launched[-1]["resume"] == "s-1"
    until(lambda: fake.got()[-1:] == [app.HANDBACK_PROMPT])
    serve.apps.stop(member.path)


def test_people_can_start_and_stop_their_own_agent_without_a_screen(lead, tmp_path):
    fake = Fake(tmp_path)
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    doc = serve.handle(lead.root, {"id": "s", "args": ["agent", "start", "--app", "--role", "lead", "--prompt", "計画して"],
                                   "cwd": "."})
    assert doc["ok"] and doc["result"]["role"] == "lead" and fake.launched[0]["root"] == lead.root
    until(lambda: fake.got() == ["計画して"])
    assert not serve.handle(lead.root, {"id": "x", "args": ["agent", "start", "--app"], "cwd": "."})["ok"]   # 2つは動かさない
    assert not serve.handle(lead.root, {"id": "y", "args": ["agent", "start"], "cwd": "."})["ok"]   # 新しい画面は係でない
    assert serve.handle(lead.root, {"id": "z", "args": ["agent", "stop"], "cwd": "."})["ok"]
    assert not serve.apps.holds(lead.root)


def test_the_cli_reads_the_log_and_asks_the_serve(lead, tmp_path, monkeypatch):
    """CLI：team log（--json・--after）、agent start --app・agent status・agent stop、team takeover・handback は係に頼む。"""
    member = team.create(lead, "画面", "目的：画面を作る")
    fake = Fake(tmp_path)
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    stop = threading.Event()
    threading.Thread(target=agent_serve.serve_forever, args=(serve, stop, 0.1), daemon=True).start()
    monkeypatch.chdir(lead.root)
    runner = CliRunner()
    invoke = lambda *args: json.loads(runner.invoke(build_cli(), [*args, "--json"], catch_exceptions=False).stdout)
    try:
        serve.apps.start(member.path, role="worker", prompt="はじめて")
        until(lambda: state(member.path).get("replied_at"))
        log = invoke("agent", "team", "log", "画面")
        assert log["ok"] and log["result"]["events"][-1]["type"] == "result"
        assert log["result"]["activity"]["mode"] == agent_status.APP
        later = invoke("agent", "team", "log", "画面", "--after", str(log["result"]["next"]))
        assert later["result"]["events"] == [] and later["result"]["next"] == log["result"]["next"]
        human = runner.invoke(build_cli(), ["agent", "team", "log", "画面"], catch_exceptions=False).stdout
        assert "▶ 入力：はじめて" in human and "・Bash：ecobuild test" in human and "■ 返答の終わり" in human
        listed = invoke("agent", "team", "list")["result"]["members"][0]
        assert listed["mode"] == agent_status.APP and listed["state"] == agent_status.IDLE

        taken = invoke("agent", "team", "takeover", "画面", "--no-open")
        assert taken["ok"] and taken["result"]["agent"] == "claude --resume s-1"
        given = invoke("agent", "team", "handback", "画面")
        assert given["ok"] and given["result"]["app"]
        until(lambda: fake.got()[-1:] == [app.HANDBACK_PROMPT])

        started = invoke("agent", "start", "--app", "--prompt", "進めて")
        assert started["ok"] and Path(started["result"]["path"]) == lead.root
        until(lambda: state(lead.root).get("replied_at"))
        status = invoke("agent", "status")["result"]
        assert status["mode"] == agent_status.APP and status["last_reply"].startswith("了解：") and status["session"]
        own = invoke("agent", "log")["result"]
        assert any(e.get("result") == "了解：進めて" for e in own["events"])
        assert "進めて" in fake.got()   # 進行役（アプリ用）には、作業役の返答の終わりの知らせも標準入力で届く
        assert invoke("agent", "stop")["ok"] and not serve.apps.holds(lead.root)
    finally:
        stop.set()
        serve.apps.stop(member.path, 5)


def test_the_team_list_has_the_nested_team_and_recent_lines(lead, tmp_path, monkeypatch):
    """team list --nested：下の進行役のチームを members に入れ子で。--recent N：1人ごとに最新の出来事の人向けの行（GUI の
    一覧・格子）。出来事のファイルは終わりだけを読む（途中から読んだ欠けた行は捨てる）。"""
    def member(root: Path, name: str, role: str) -> Path:
        folder = root / team.TEAM_AREA / f"1-{name}"
        (folder / ".ecobuild" / "ai").mkdir(parents=True)
        (folder / team.MEMBER_FILE).write_text(json.dumps({"name": name, "role": role, "task": 1}), encoding="utf-8")
        return folder

    sub = member(lead.root, "下の管理役", team.MANAGER)
    worker = member(sub, "画面", team.WORKER)
    folder = agent_status.prepare(container.name(worker), worker)
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
    plain = invoke("agent", "team", "list")["result"]["members"]
    assert [m["name"] for m in plain] == ["下の管理役"] and "members" not in plain[0] and "recent" not in plain[0]
    nested = invoke("agent", "team", "list", "--nested", "--recent", "2")["result"]["members"]
    assert nested[0]["recent"] == [] and [m["name"] for m in nested[0]["members"]] == ["画面"]
    assert nested[0]["members"][0]["recent"] == ["  ・Bash：ecobuild test", "◀ できました"]
    human = CliRunner().invoke(build_cli(), ["agent", "team", "list", "--nested"], catch_exceptions=False).stdout
    assert "管理役「下の管理役」" in human and "\n    作業役「画面」" in human


def test_the_launch_is_made_like_the_interactive_one(lead, monkeypatch):
    """起動のしかた（AgentModule.app_launch）：コンテナの中の claude -p の stream-json。会話の ID・役・モデル・使い方の文は
    対話型と同じ作り方。statusLine・返答の終わりのフックは付けない（進行役の書ける場所のフックは付ける）。"""
    from ecobuild import config
    import ecobuild_bundle
    config.save_local(lead.root, {"container": True})
    ecobuild_bundle.set_config("agent_lead_model", "opus")
    seen = {}

    def launch(root, agent, **options):
        seen.update(agent=agent, **options)
        return ["docker", "exec", "--interactive", *agent], {"X": "1"}
    monkeypatch.setattr(inside, "agent_launch", launch)
    found = lead.app_launch(role="lead")
    command = seen["agent"]
    assert command[:8] == ("claude", *app.FLAGS) and seen["stdin"] and not seen["tty"] and seen["tag"]
    assert command[command.index("--session-id") + 1] == found.session and found.role == "lead"
    assert team.remembered_roles(lead.root)[found.session] == "lead"
    assert command[command.index("--model") + 1] == "opus"
    assert command[command.index("--append-system-prompt-file") + 1] == f"{agent_status.INSIDE}/guide.md"
    settings = json.loads((found.folder / agent_status.SETTINGS).read_text(encoding="utf-8"))
    assert "statusLine" not in settings and list(settings["hooks"]) == ["PreToolUse"]       # 進行役の書ける場所だけ
    assert "進行役" in (found.folder / "guide.md").read_text(encoding="utf-8")
    again = lead.app_launch(resume=found.session)
    assert "--session-id" not in seen["agent"] and seen["agent"][seen["agent"].index("--resume") + 1] == found.session
    assert again.role == "lead"                                                          # 覚えた役で続きから


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def test_a_second_agent_is_not_started_while_one_is_alive(lead):
    """生きている running.json があると、2つ目（対話型・アプリ用）は起動しない。死んだ pid なら起動を止めない。"""
    import subprocess
    folder = agent_status.directory(container.name(lead.root))
    folder.mkdir(parents=True, exist_ok=True)
    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        agent_status.started(folder, live.pid)
        with pytest.raises(EcoBuildError) as stopped:
            lead._no_other_agent(wait=0)
        assert stopped.value.code == ErrorCode.AGENT_ERROR and str(live.pid) in str(stopped.value)
        assert code_of(lambda: lead.start_agent(("claude",))) == ErrorCode.AGENT_ERROR
        assert code_of(lambda: lead.app_launch()) == ErrorCode.AGENT_ERROR
    finally:
        live.kill()
        live.wait()
    lead._no_other_agent(wait=0)   # 終わった pid では止めない（起動し直しの後）
