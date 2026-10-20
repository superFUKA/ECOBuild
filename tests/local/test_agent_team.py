"""進行役と作業役（ecobuild_agent.team）：作業役は子タスク＋進行役の作業空間の中の作業空間。"""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from fakes import FakeGitHub
import ecobuild_bundle
import ecobuild_container as container
from ecobuild import workspaces
from ecobuild_agent import serve as agent_serve
from ecobuild_agent import status as agent_status
from ecobuild_agent import team
from ecobuild_agent.errors import ErrorCode
from ecobuild_bundle import Module
from ecowork import WorkError

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
    ecobuild_bundle.set_config("agent_worker_model", "haiku")
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
    assert "提出しない" in briefing                                                   # レビュー・調べものは報告だけ

    (member.path / team.REPORT_FILE).unlink()
    closed = Module.close_workspace(member.path)                                            # 入れ子でも閉じられる
    assert closed.done and not member.path.exists() and team.team(lead.root).members == ()


def test_a_worker_takes_over_the_leads_container(lead):
    """進行役の作業空間がコンテナなら、作業役の作業空間もコンテナ（同じイメージの指定・使わせないもの）。"""
    from ecobuild import config
    config.save_local(lead.root, {"container": True, "agent_deny": "WebFetch", "profile": "Release"})
    member = team.create(lead, "画面", "目的：作る")
    local = config.load_local(member.path)
    assert local["container"] is True and local["agent_deny"] == "WebFetch" and "profile" not in local   # コンテナのものだけ


def test_a_lead_has_its_own_model_and_writes_only_its_notes(lead, tmp_path):
    ecobuild_bundle.set_config("agent_lead_model", "opus")
    assert team.agent_options(lead.root, team.LEAD, ("claude",)) == ("claude", "--model", "opus")
    lead._status_settings(tmp_path, False, app=True, role=team.LEAD)
    settings = json.loads((tmp_path / agent_status.SETTINGS).read_text(encoding="utf-8"))
    guard = settings["hooks"]["PreToolUse"][0]
    assert "Write" in guard["matcher"] and guard["hooks"][0]["command"].endswith(
        f'lead-edit "{(lead.root / ".ecobuild/ai").as_posix()}"')                      # 書けるのは .ecobuild/ai だけ
    lead._status_settings(tmp_path, True, app=True, role=team.WORKER)
    assert "PreToolUse" not in json.loads((tmp_path / agent_status.SETTINGS).read_text(encoding="utf-8"))["hooks"]
    assert team.agent_options(lead.root, team.LEAD, ("claude", "--model", "sonnet"))[:3] == ("claude", "--model", "sonnet")
    assert team.agent_options(lead.root, team.LEAD, ("codex",)) == ("codex",)               # Claude Code だけ
    sub = team.create(lead, "下の進行役", "この部分を受け持つ", role=team.LEAD, model="sonnet")
    assert team.role_of(sub.path) == team.LEAD and sub.prompt == team.FIRST_PROMPT[team.LEAD]
    assert team.agent_options(sub.path, team.LEAD, ("claude",))[:3] == ("claude", "--model", "sonnet")   # 作ったときの指定
    briefing = lead.agent_briefing(lead.require_task_branch("x"), team.LEAD)
    assert "進行役" in briefing and "agent team start" in briefing and team.PLAN_FILE in briefing
    assert "進め方の手" in briefing and "2〜3人" not in briefing                          # 人数は大きさ・独立さで
    assert all(word in briefing for word in ("共通の決まり", "レビュー", "アイデア", "--lead", "task close"))
    assert code_of(lambda: team.create(lead, "空", "  ")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: team.role_of(lead.root, "boss")) == ErrorCode.INVALID_ARGUMENT


def test_the_first_prompt_goes_right_after_claude(lead):
    command = lead._for_role(("claude",), team.LEAD, "始めて")
    assert command[:2] == ("claude", "始めて")   # 値を何個も取る引数（--disallowedTools 等）の値に読まれない


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


def test_closing_the_lead_checks_and_forgets_the_workers(lead):
    """進行役の作業空間を閉じると中の作業役の作業空間も消えるので、作業役の GitHub にないものも確かめ、記録からも外す。"""
    member = team.create(lead, "画面", "目的：画面を作る")
    (member.path / "new.txt").write_text("まだ\n", encoding="utf-8")                  # 作業役の未コミットの変更
    with pytest.raises(WorkError) as error:
        Module.close_workspace(lead.root)
    assert error.value.code == ErrorCode.UNFINISHED_WORK and lead.root.exists()
    assert any(item.startswith(f"{team.TEAM_AREA}/{member.path.name}：") for item in error.value.details)
    (member.path / "new.txt").unlink()
    assert Module.close_workspace(lead.root).done and not lead.root.exists()
    assert not any(workspaces.same(item.path, member.path) for item in workspaces.recorded())


def test_the_serve_answers_requests_and_tells_the_lead(lead):
    """係：頼みを実行して結果を書き戻し、作業役ができたら起動を頼み、作業役の返答の終わりを進行役に知らせる。"""
    member = team.create(lead, "画面", "目的：画面を作る")
    folder = agent_status.prepare(container.name(lead.root), lead.root)
    agent_status.prepare(container.name(member.path), member.path)
    events, ran = [], []

    def run(args, cwd, **_):
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
    serve.wait()
    result = lambda key: json.loads((requests / f"{key}.result.json").read_text(encoding="utf-8"))
    assert result("a")["ok"] and events[0] == {"event": "agent-start", "path": str(member.path), "name": "画面",
                                               "role": "worker", "prompt": "読んで", "lead": str(lead.root)}
    assert not result("b")["ok"] and not result("c")["ok"]                             # チームの操作だけ・作業空間の中だけ
    assert [a for a, _ in ran] == [["agent", "team", "start", "画面", "--json"]]
    assert not list(requests.glob("*.taken"))

    (requests / "d.json").write_text(json.dumps({"id": "d", "args": ["agent", "team", "close", "画面"], "cwd": "."}),
                                     encoding="utf-8")
    serve.step()
    serve.wait()
    assert events[1]["event"] == "agent-stop" and events[1]["path"] == str(member.path)   # 閉じる前に止めてもらう
    assert ran[-1][0] == ["agent", "team", "close", "画面"]

    member_folder = team.inbox_of(member.path)
    (member_folder / "replied.json").write_text(json.dumps({"at": serve.started + 5, "message": "終わりました"}),
                                                encoding="utf-8")
    serve.step()
    serve.wait()
    notice = agent_status.take(folder)
    assert "作業役「画面」" in notice["text"] and notice["text"].endswith("終わりました")
    assert ran[-1] == (["project", "update"], member.path)                               # 型に手元をそろえさせる
    serve.step()
    serve.wait()
    assert agent_status.take(folder) is None                                             # 同じ返答は1回だけ


def test_a_long_request_does_not_keep_others_waiting(lead):
    """長くかかる頼み（作業役を作る clone 等）を実行している間も、ほかの頼みはすぐに拾う（頼んだ側が「係がいない」と
    思わない）。同じ置き場所のものは順に、別の置き場所のものは並べて実行する。"""
    member = team.create(lead, "画面", "目的：画面を作る")
    folders = [agent_status.prepare(container.name(lead.root), lead.root),
               agent_status.prepare(container.name(member.path), member.path)]
    release, ran = threading.Event(), []

    def run(args, cwd, **_):
        ran.append(args[3])
        if args[3] == "a":
            assert release.wait(10)
        return {"ok": True, "result": {}}

    serve = agent_serve.Serve(run, emit=lambda event: None)
    for folder, keys in zip(folders, ("ab", "c")):
        (folder / team.REQUESTS).mkdir(exist_ok=True)
        for key in keys:
            (folder / team.REQUESTS / f"{key}.json").write_text(
                json.dumps({"id": key, "args": ["agent", "team", "list", key], "cwd": "."}), encoding="utf-8")
    serve.step()
    assert not [f for folder in folders for f in (folder / team.REQUESTS).glob("?.json")]   # すぐに全部拾った
    for _ in range(100):
        if (folders[1] / team.REQUESTS / "c.result.json").exists():
            break
        time.sleep(0.05)
    assert (folders[1] / team.REQUESTS / "c.result.json").exists() and "b" not in ran   # 別の置き場所は待たない
    release.set()
    serve.wait()
    assert ran.index("a") < ran.index("b") and (folders[0] / team.REQUESTS / "b.result.json").exists()


def test_without_an_app_the_serve_opens_the_worker_itself(lead):
    opened = []
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {"path": "/w", "name": "x", "role": "worker",
                                                                            "prompt": "p"}},
                              open_agent=lambda path, role, prompt, agent: opened.append((path, role, prompt, agent)))
    doc = serve.handle(lead.root, {"id": "a", "args": ["agent", "team", "start", "x"], "cwd": "."})
    assert doc["result"]["opened"] and opened == [(Path("/w"), "worker", "p", "")]


def test_the_serve_runs_commands_while_reading_the_apps_replies(tmp_path):
    # 係は起動したアプリの返事（標準入力）を読み続けている。その間に実行するコマンドが止まらない
    # （Windows では、読みかけのパイプを引き継いだ Python が起動の途中で止まり、作業役が作られなかった）。
    script = ("import sys, threading, time, json\n"
              "from pathlib import Path\n"
              "from ecobuild_cli.commands.agent.serve import run\n"
              "threading.Thread(target=sys.stdin.readline, daemon=True).start()\n"
              "time.sleep(0.5)\n"
              "print(json.dumps(run(['status'], Path(sys.argv[1]))))\n")
    process = subprocess.Popen([sys.executable, "-c", script, str(tmp_path)], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, encoding="utf-8")
    try:
        process.wait(timeout=60)   # 標準入力は開いたまま（アプリが係を動かしている間と同じ）
    except subprocess.TimeoutExpired:
        process.kill()
        pytest.fail("係の実行したコマンドが、標準入力を引き継いで止まりました")
    finally:
        process.stdin.close()
    assert json.loads(process.stdout.read())


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


def test_the_team_shows_how_each_member_is_doing(lead):
    """team list：作業役の様子（作業中・待機中・止まっている）と最後の返答。"""
    import os
    member = team.create(lead, "画面", "目的：画面を作る")
    assert team.find(lead.root, "画面").state == agent_status.STOPPED
    folder = agent_status.prepare(container.name(member.path), member.path)
    (folder / agent_status.RUNNING).write_text(json.dumps({"pid": os.getpid(), "at": time.time() - 600}), encoding="utf-8")
    (folder / "replied.json").write_text(json.dumps({"at": time.time() - 125, "message": "ボタンの位置で迷っています"}),
                                         encoding="utf-8")
    found = team.find(lead.root, "画面")
    assert found.state == agent_status.IDLE and found.last_reply == "ボタンの位置で迷っています"
    assert team.describe_activity(found.__dict__).startswith("待機中（2分）")


def test_restarting_keeps_the_work_and_starts_a_new_or_the_same_conversation(lead):
    member = team.create(lead, "画面", "目的：画面を作る")
    plan = team.restart_plan(lead.root, "画面")
    assert plan.path == member.path and plan.prompt == team.RESTART_PROMPT[team.WORKER] and not plan.agent
    assert code_of(lambda: team.restart_plan(lead.root, "画面", resume=True)) == ErrorCode.INVALID_ARGUMENT  # 会話が分からない
    folder = agent_status.prepare(container.name(member.path), member.path)
    (folder / "status.json").write_text(json.dumps({"session": "s-1"}), encoding="utf-8")
    plan = team.restart_plan(lead.root, "画面", resume=True)
    assert plan.agent == "claude --resume s-1" and plan.prompt == team.RESUME_PROMPT


def test_the_serve_restarts_a_member_and_reports_progress(lead):
    """係：起動し直す頼みは、止めてもらってから起動のしかたを聞き、起動を頼む。実行中は途中経過を書き、終われば消す。"""
    member = team.create(lead, "画面", "目的：画面を作る")
    folder = agent_status.prepare(container.name(lead.root), lead.root)
    events, seen = [], []
    requests = folder / team.REQUESTS
    requests.mkdir()

    def run(args, cwd, progress=None, stall=None):
        assert stall == team.STALL_SECONDS
        progress("起動のしかたを調べています…")
        seen.append(json.loads((requests / f"r{team.PROGRESS}").read_text(encoding="utf-8")))
        return {"ok": True, "result": {"path": str(member.path), "name": "画面", "role": "worker", "prompt": "続けて",
                                       "agent": "claude --resume s-1", "args": args}}

    serve = agent_serve.Serve(run, emit=events.append, ack=lambda key, timeout: True)
    (requests / "r.json").write_text(json.dumps({"id": "r", "args": ["agent", "team", "restart", "画面", "--resume",
                                                                     "--json"], "cwd": "."}), encoding="utf-8")
    serve.step()
    serve.wait()
    result = json.loads((requests / "r.result.json").read_text(encoding="utf-8"))
    assert result["ok"] and result["result"]["args"][-1] == "--no-open"                # 起動は係が頼む
    assert [e["event"] for e in events] == ["agent-stop", "agent-start"] and events[1]["agent"] == "claude --resume s-1"
    assert seen[0]["doing"] == "起動のしかたを調べています…" and seen[0]["at"] >= seen[0]["since"]
    assert not (requests / f"r{team.PROGRESS}").exists()                               # 終わったら消す


def test_waiting_shows_the_serves_progress_and_stops_when_the_serve_is_gone(lead, monkeypatch):
    monkeypatch.setenv(team.WINDOW_VARIABLE, "1")
    folder = team.requests_folder(lead.root)
    told = []

    def serve(answer):
        def wait(seconds):   # 係のふり：拾って途中経過を書き、answer なら結果も
            for request in folder.glob("*.json"):
                if request.name.endswith(".result.json"):
                    continue
                key = request.stem
                request.rename(request.with_suffix(".taken"))
                at = time.time() if answer else time.time() - team.SERVE_SILENT - 5
                (folder / f"{key}{team.PROGRESS}").write_text(json.dumps({"doing": "clone しています", "at": at}),
                                                             encoding="utf-8")
                if answer:
                    (folder / f"{key}.result.json").write_text(json.dumps({"ok": True, "result": {}}), encoding="utf-8")
        return wait
    assert team.forward(lead.root, ["agent", "team", "list"], lead.root, wait=serve(True), progress=told.append)["ok"]
    assert code_of(lambda: team.forward(lead.root, ["agent", "team", "list"], lead.root, wait=serve(False),
                                        progress=told.append)) == ErrorCode.AGENT_ERROR   # 係の印が途切れた
    assert told and told[-1] == "係：clone しています"


def test_the_serve_stops_a_command_that_makes_no_progress(tmp_path, monkeypatch):
    """係の実行した ecobuild が経過を出さなくなったら、止めて失敗を返す（頼んだ側を待たせ続けない）。"""
    from ecobuild_cli.commands.agent import serve as serve_command
    quiet = "import sys, time; print('始めました', file=sys.stderr, flush=True); time.sleep(60)"
    monkeypatch.setattr(serve_command, "PROGRAM", (sys.executable, "-c", quiet))
    lines = []
    started = time.monotonic()
    doc = serve_command.run(["agent", "team", "list"], tmp_path, progress=lines.append, stall=2)
    assert not doc["ok"] and "止まっていました" in doc["error"]["message"] and lines == ["始めました"]
    assert time.monotonic() - started < 30


def test_waiting_stops_when_the_serve_took_the_request_but_never_answers(lead, monkeypatch):
    """拾ったのに途中経過を書かない係（消えた・古い ECOBuild の係）も待ち続けない。"""
    monkeypatch.setenv(team.WINDOW_VARIABLE, "1")
    monkeypatch.setattr(team, "SERVE_SILENT", 0.3)
    folder = team.requests_folder(lead.root)

    def take(seconds):
        for request in folder.glob("*.json"):
            request.rename(request.with_suffix(".taken"))
        time.sleep(0.1)
    started = time.monotonic()
    assert code_of(lambda: team.forward(lead.root, ["agent", "team", "list"], lead.root, wait=take)) \
        == ErrorCode.AGENT_ERROR
    assert time.monotonic() - started < 10


def test_stopping_the_serve_waits_only_a_little_for_running_requests(lead):
    release = threading.Event()
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}})
    serve._later(lead.root, lambda: release.wait(10))
    assert serve.wait(0.2) is False                                                     # 終わらなければ待ちきらない
    release.set()
    assert serve.wait(5) is True


def test_the_serve_does_not_take_its_own_progress_for_requests(lead):
    """途中経過・結果は頼みとして拾わない（拾うと途中経過が消え、頼んだ側が「応えない」と止まった）。"""
    folder = agent_status.prepare(container.name(lead.root), lead.root)
    requests = folder / team.REQUESTS
    requests.mkdir()
    release, ran = threading.Event(), []

    def run(args, cwd, **_):
        ran.append(args)
        assert release.wait(10)
        return {"ok": True, "result": {}}
    serve = agent_serve.Serve(run)
    (requests / "a.json").write_text(json.dumps({"id": "a", "args": ["agent", "team", "list"], "cwd": "."}),
                                     encoding="utf-8")
    for _ in range(3):   # 実行中に何度も見回る
        serve.step()
        time.sleep(0.05)
    assert sorted(p.name for p in requests.iterdir()) == sorted(["a.taken", f"a{team.PROGRESS}"])
    release.set()
    serve.wait()
    assert len(ran) == 1 and sorted(p.name for p in requests.iterdir()) == ["a.result.json"]


def test_children_of_the_serve_do_not_inherit_the_apps_pipe(tmp_path):
    """係がアプリの返事を読んでいる間に起動する git 等も止まらない（標準入力を係だけのものにする）。"""
    script = ("import subprocess, sys, threading, time\n"
              "from ecobuild_cli.commands.agent.serve import detach_stdin\n"
              "replies = detach_stdin()\n"
              "threading.Thread(target=replies.readline, daemon=True).start()\n"
              "time.sleep(0.5)\n"
              "print(subprocess.run(['git', '--version'], capture_output=True, text=True, timeout=20).returncode)\n")
    process = subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               encoding="utf-8")
    try:
        process.wait(timeout=40)   # 標準入力は開いたまま
    except subprocess.TimeoutExpired:
        process.kill()
        pytest.fail("係の起動した git が、アプリのパイプを引き継いで止まりました")
    finally:
        process.stdin.close()
    assert process.stdout.read().strip() == "0"


def test_the_serve_runs_a_type_command_only_for_that_type(lead):
    """返答のたびの project update（C++ の型のコマンド）を、ほかの型のモジュールでは実行しない（ログにエラーを残さない）。"""
    from ecobuild_cli.commands.agent import serve as serve_command
    assert not serve_command.type_has(["project", "update"], lead.root)                 # generic の型
    assert serve_command.type_has(["agent", "team", "list"], lead.root)                 # 型のコマンドでないもの
    doc = serve_command.run(["project", "update"], lead.root)
    assert not doc["ok"] and "型のコマンドではありません" in doc["error"]["message"]
