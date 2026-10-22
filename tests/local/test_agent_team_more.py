"""チームの操作の点検の直し（Issue #10）：名前の取り違え・言付けの番号・知らせのまとめ・閉じる前の確かめ 等。"""

import json
import time

import pytest
from click.testing import CliRunner

from fakes import FakeGitHub
import ecobuild_container as container
from ecobuild_agent import serve as agent_serve
from ecobuild_agent import status as agent_status
from ecobuild_agent import team
from ecobuild_agent.errors import ErrorCode
from ecobuild_bundle import Module
from ecobuild_cli import build_cli
from ecowork import WorkError

pytestmark = pytest.mark.local


def failure(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value


@pytest.fixture
def lead(tmp_path, monkeypatch):
    from ecowork import github as ecowork_github
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    monkeypatch.delenv(team.WINDOW_VARIABLE, raising=False)
    monkeypatch.delenv(team.OWNER_VARIABLE, raising=False)
    github = FakeGitHub(tmp_path / "gh")
    monkeypatch.setattr(ecowork_github, "default", lambda: github)
    monkeypatch.setattr(team, "RETRY_WAIT", (0, 0, 0))   # 一時的な失敗のやり直しを待たない
    module = Module.create("Plain", directory=tmp_path, type="generic", github=github)
    module.repository.create_task("大きな仕事").start(name="大きな仕事")
    (module.root / team.MEMBER_FILE).parent.mkdir(parents=True, exist_ok=True)
    (module.root / team.MEMBER_FILE).write_text(json.dumps({"role": team.MANAGER}), encoding="utf-8")   # 作業役を作れる役
    return module


@pytest.fixture
def cli(lead, monkeypatch):
    monkeypatch.chdir(lead.root)
    runner = CliRunner()

    def invoke(*args):
        result = runner.invoke(build_cli(), [*args, "--json"], catch_exceptions=False)
        return json.loads(result.stdout)
    return invoke


# ---- 53：名前で探す ---------------------------------------------------------------------------------------------

def test_a_name_that_fits_two_members_stops_with_the_candidates(lead):
    first = team.create(lead, "画面", "目的：画面")
    second = team.create(lead, "保存", "目的：保存")
    info = json.loads((second.path / team.MEMBER_FILE).read_text(encoding="utf-8"))
    (second.path / team.MEMBER_FILE).write_text(json.dumps({**info, "name": str(first.task)}), encoding="utf-8")
    error = failure(lambda: team.find(lead.root, str(first.task)))                 # 甲の番号＝乙の名前
    assert error.code == ErrorCode.INVALID_ARGUMENT and "2 人" in error.message
    assert any(first.path.name in line for line in error.details) and any(second.path.name in line for line in error.details)
    assert team.find(lead.root, first.path.name).task == first.task               # フォルダー名なら1人
    assert failure(lambda: team.create(lead, "123", "目的：x")).code == ErrorCode.INVALID_ARGUMENT   # 番号だけの名前


# ---- 49・52：CLI -------------------------------------------------------------------------------------------------

def test_the_brief_file_is_read_without_the_bom(lead, cli, tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_bytes("﻿目的：画面を作る\n".encode("utf-8"))
    doc = cli("agent", "team", "start", "画面", "--brief-file", str(brief), "--no-open")
    assert doc["ok"], doc
    path = lead.root / team.TEAM_AREA / f"{doc['result']['task']}-画面"
    assert (path / team.BRIEF_FILE).read_text(encoding="utf-8").startswith("目的")
    assert lead.repository.github.issues[doc["result"]["task"]].body.startswith("目的")


def test_restart_without_opening_still_stops_the_agent(lead, cli, monkeypatch):
    team.create(lead, "画面", "目的：画面")
    stopped = []
    monkeypatch.setattr(agent_status, "running_pid", lambda folder: 4321)
    monkeypatch.setattr(agent_status, "stop", stopped.append)
    doc = cli("agent", "team", "restart", "画面", "--no-open")
    assert doc["ok"] and stopped == [4321] and not doc["result"]["opened"]


# ---- 20：言付けの番号 ------------------------------------------------------------------------------------------

def test_a_message_has_an_id_and_can_be_cancelled_or_replaced_before_it_arrives(lead, cli):
    member = team.create(lead, "画面", "目的：画面")
    sent = cli("agent", "team", "send", "画面", "ボタンは右に")
    key = sent["result"]["message_id"]
    assert sent["ok"] and len(key) == 8
    listed = cli("agent", "team", "list")["result"]["members"][0]
    assert [(m["id"], m["delivered"]) for m in listed["messages"]] == [(key, False)]
    replaced = cli("agent", "team", "send", "画面", "ボタンは左に", "--replace", key)
    new = replaced["result"]["message_id"]
    assert replaced["ok"] and new != key
    got = agent_status.take(team.inbox_of(member.path))
    assert got["text"].endswith("ボタンは左に") and agent_status.take(team.inbox_of(member.path)) is None
    messages = {m["id"]: m for m in team.messages(team.inbox_of(member.path))}
    assert messages[key]["cancelled"] and not messages[key]["delivered"] and messages[new]["delivered"]
    late = cli("agent", "team", "send", "画面", "--cancel", new)                  # 届いた後は取り消せない
    assert not late["ok"] and "もう届いています" in late["error"]["message"]
    assert not cli("agent", "team", "send", "画面", "--cancel", "nothing1")["ok"]


# ---- 4・19・30：返答の終わりの知らせ ----------------------------------------------------------------------------

def test_the_notice_tells_the_state_and_how_old_the_report_is(lead):
    member = team.create(lead, "画面", "目的：画面")
    folder = team.inbox_of(member.path)
    (member.path / team.REPORT_FILE).write_text("できた\n", encoding="utf-8")
    import os
    os.utime(member.path / team.REPORT_FILE, (time.time() - 600, time.time() - 600))
    team.send(lead.root, "画面", "もう一度")
    agent_status.write_reply(folder, "途中")
    agent_status.write_reply(folder, "直しました\n状態：続ける")
    _, text = team.lead_notice(member.path, "直しました\n状態：続ける")
    assert f"子タスク #{member.task}・返答 2 回目" in text
    assert "最後の言付けより前（言付けの後は書き直していません）" in text and "届いていない言付け 1 件" in text
    assert team.saved_facts(member.path)["state"] == team.GOING                        # team list が読む
    _, short = team.lead_notice(member.path, "", continued=2)
    assert "言付け 2 件を受け取って続けています" in short and "注意" not in short


def test_the_serve_passes_only_the_latest_notice_of_a_member(lead):
    member = team.create(lead, "画面", "目的：画面")
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, background=False)
    inbox = team.inbox_of(lead.root)
    serve.replied(member.path, "一回目\n状態：続ける")
    serve.replied(member.path, "二回目\n状態：完了")
    agent_status.put(inbox, "ほかの言付け", sender="someone")
    first = agent_status.take(inbox)
    assert "二回目" in first["text"] and "前の知らせ 1 件を、これにまとめました" in first["text"]
    assert agent_status.take(inbox)["text"] == "ほかの言付け" and agent_status.take(inbox) is None


def test_the_stop_hook_tells_that_it_goes_on_with_the_messages(lead, tmp_path):
    """Stop フック（対話型）：受け箱のものを渡して続けさせるときは、そう書く（係は「返答が終わりました」と言わない）。"""
    import subprocess
    import sys
    folder = agent_status.prepare("x", tmp_path)
    agent_status.put(folder, "言付け")
    run = lambda: subprocess.run([sys.executable, str(folder / agent_status.SCRIPT), "replied", "deliver"],
                                 input=json.dumps({"last_assistant_message": "途中"}).encode("utf-8"), capture_output=True)
    assert json.loads(run().stdout)["decision"] == "block"
    assert agent_status.read(folder / "replied.json")["continued"] == 1
    assert run().stdout == b"" and "continued" not in agent_status.read(folder / "replied.json")
    assert agent_status.replies(folder) == 2


# ---- 3・5・21：閉じる -------------------------------------------------------------------------------------------

def test_closing_checks_the_work_keeps_the_report_and_forgets_the_inbox(lead, cli):
    member = team.create(lead, "画面", "目的：画面")
    (member.path / team.REPORT_FILE).write_text("できた\n", encoding="utf-8")
    team.send(lead.root, "画面", "まだ届かない")
    agent_status.put(team.inbox_of(lead.root), "画面の知らせ", sender=str(member.path), kind=agent_status.NOTICE)
    refused = cli("agent", "team", "close", "画面")
    assert not refused["ok"] and refused["error"]["code"] == ErrorCode.UNFINISHED_WORK
    assert any("届いていない言付け" in line for line in refused["error"]["details"])
    preview = cli("agent", "team", "close", "画面", "--dry-run")
    assert preview["ok"] and preview["result"]["problems"] and member.path.exists()
    assert sorted(preview["result"]["archive"]) == sorted([f"{team.ARCHIVE}/{member.path.name}/report.md",
                                                           f"{team.ARCHIVE}/{member.path.name}/brief.md"])
    (member.path / "新しい.txt").write_text("x\n", encoding="utf-8")
    unpushed = cli("agent", "team", "close", "画面", "--force")
    assert not unpushed["ok"] and "ファイル：新しい.txt" in unpushed["error"]["details"]
    (member.path / "新しい.txt").unlink()
    closed = cli("agent", "team", "close", "画面", "--force")
    assert closed["ok"] and not member.path.exists()
    kept = lead.root / team.ARCHIVE / member.path.name
    assert (kept / "report.md").read_text(encoding="utf-8") == "できた\n" and (kept / "brief.md").is_file()
    assert not (team.inbox_of(member.path) / agent_status.INBOX).exists()
    assert agent_status.take(team.inbox_of(lead.root)) is None                         # 閉じた作業役の知らせも消す


def test_closing_several_and_the_merged_ones(lead, cli):
    made = [team.create(lead, name, f"目的：{name}") for name in ("画面", "保存", "検索")]
    both = cli("agent", "team", "close", "画面", "保存")
    assert both["ok"] and [c["name"] for c in both["result"]["closed"]] == ["画面", "保存"]
    worker = Module.find(made[2].path, github=lead.repository.github)
    (worker.root / "a.txt").write_text("a\n", encoding="utf-8")
    worker.require_task_branch("x").stage("a.txt")
    worker.require_task_branch("x").commit("a")
    pr = worker.submit(check=False)
    assert cli("agent", "team", "close", "--merged")["result"]["closed"] == []           # まだ取り込んでいない
    import dataclasses
    pulls = lead.repository.github.pulls
    pulls[pr.number] = dataclasses.replace(pulls[pr.number], state="merged")
    closed = cli("agent", "team", "close", "--merged")
    assert [c["name"] for c in closed["result"]["closed"]] == ["検索"] and not made[2].path.exists()


def test_accept_finishes_syncs_and_closes_or_does_nothing(lead, cli):
    """#10-41：agent team accept は close と同じことを確かめ、task finish → sync → close を一度にする。"""
    member = team.create(lead, "画面", "目的：画面")
    worker = Module.find(member.path, github=lead.repository.github)
    (worker.root / "a.txt").write_text("a\n", encoding="utf-8")
    worker.require_task_branch("x").stage("a.txt")
    worker.require_task_branch("x").commit("a")
    worker.submit(check=False)
    team.send(lead.root, "画面", "まだ届かない")
    refused = cli("agent", "team", "accept", "画面")
    assert not refused["ok"] and refused["error"]["code"] == ErrorCode.UNFINISHED_WORK and member.path.exists()
    assert lead.repository.task(member.task).state == "open"                            # 取り込んでいない
    agent_status.take(team.inbox_of(member.path))                                        # 届いた
    accepted = cli("agent", "team", "accept", "画面")
    assert accepted["ok"], accepted
    result = accepted["result"]
    assert result["task"] == member.task and result["finish"]["task"] == member.task and "branch" in result["sync"]
    assert result["closed"]["name"] == "画面" and not member.path.exists()
    assert (lead.root / "a.txt").is_file()                                               # sync で手元に


def test_the_list_shows_what_the_serve_saw_and_the_messages(lead, cli):
    member = team.create(lead, "画面", "目的：画面")
    (member.path / "x.txt").write_text("x\n", encoding="utf-8")
    team.lead_notice(member.path, "状態：続ける")                                        # 係が返答の終わりに調べる
    listed = cli("agent", "team", "list")["result"]["members"][0]
    assert listed["dirty"] == ["x.txt"] and listed["ahead"] == 0 and listed["submission"] is None
    assert listed["messages"] == [] and listed["replies"] == 0 and listed["report_at"] is None


# ---- 13：作成の一時的な失敗・作業空間のない子タスク ------------------------------------------------------------

def test_a_temporary_github_failure_is_tried_again(lead, monkeypatch):
    """5xx・接続の誤りは待ってやり直す（できた子タスクはそのまま使う：二重に作らない・閉じない）。"""
    from ecotask.tracker import Tracker
    from ecowork import WorkError as Failure
    real, calls, waits = Tracker.issue, [], []

    def flaky(self, number):
        calls.append(number)
        if len(calls) <= 1:
            raise Failure("github_error", "HTTP 502 Bad Gateway")
        return real(self, number)
    monkeypatch.setattr(Tracker, "issue", flaky)
    issues = len(lead.repository.github.issues)
    member = team.create(lead, "グラフ", "目的：作る", wait=waits.append)
    assert len(lead.repository.github.issues) == issues + 1 and member.path.is_dir()
    assert lead.repository.github.issues[member.task].state == "open"


def test_a_failure_tells_what_was_made_and_a_child_without_a_workspace_can_be_used(lead, monkeypatch):
    from ecowork.git import Git
    from ecowork import WorkError as Failure
    real = Git.set_config
    waits = []

    def broken(self, key, value):
        if self.root != lead.root:
            raise Failure("github_error", "HTTP 503 Service Unavailable")
        return real(self, key, value)
    monkeypatch.setattr(Git, "set_config", broken)
    error = failure(lambda: team.create(lead, "グラフ", "目的：作る", wait=waits.append))
    assert waits == list(team.RETRY_WAIT)                                                 # 3回まで待ってやり直した
    child = max(lead.repository.github.issues)
    assert error.details[:2] == [f"子タスク：#{child}（閉じた）", "作業空間：なし"]
    monkeypatch.setattr(Git, "set_config", real)

    parent = lead.require_task_branch("x").number
    left = lead.repository.create_task("検索", body="目的：探す", parent=parent)          # 作業空間のない子タスク
    assert {"task": left.number, "title": "検索"} in team.orphans(lead)
    member = team.create(lead, "検索の続き", "目的：探す", existing=left.number)
    assert member.task == left.number and team.orphans(lead) == []
    assert failure(lambda: team.create(lead, "別", "x", existing=left.number)).code == ErrorCode.ALREADY_EXISTS
    assert failure(lambda: team.create(lead, "別", "x", existing=9999)).code == ErrorCode.INVALID_ARGUMENT


def test_transient_errors_are_told_apart():
    from ecowork import WorkError as Failure
    assert team.transient(Failure("github_error", "HTTP 502 Bad Gateway"))
    assert team.transient(Failure("github_error", "connection reset by peer"))
    assert not team.transient(Failure("github_error", "HTTP 404 Not Found"))
    assert not team.transient(Failure("x", "子タスク #503 はありません"))


# ---- 21：まとめて作る ------------------------------------------------------------------------------------------

def test_many_workers_are_made_from_a_folder_of_briefs(lead, cli, tmp_path):
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    for name in ("画面", "保存", "検索"):
        (briefs / f"{name}.md").write_text(f"目的：{name}を作る\n", encoding="utf-8")
    (briefs / "メモ.png").write_bytes(b"x")                                              # .md・.txt だけ
    doc = cli("agent", "team", "start", "--brief-dir", str(briefs), "--no-open")
    assert doc["ok"] and [m["name"] for m in doc["result"]["members"]] == sorted(["画面", "保存", "検索"])
    assert doc["result"]["failed"] == [] and len(team.team(lead.root).members) == 3
    again = cli("agent", "team", "start", "--brief-dir", str(briefs), "--no-open")       # もういる：失敗に並べる
    assert again["ok"] and again["result"]["members"] == [] and len(again["result"]["failed"]) == 3


# ---- 16・27・28・29：作業役の手順・記録・報告 ----------------------------------------------------------------

def test_a_report_only_worker_gets_its_own_words(lead):
    member = team.create(lead, "調べ", "目的：調べる", report_only=True)
    assert team.NO_SUBMIT in (member.path / team.BRIEF_FILE).read_text(encoding="utf-8")
    assert member.prompt == team.REPORT_ONLY_PROMPT and "agent report" in member.prompt
    worker = Module.find(member.path)
    role_part = "\n".join(team.briefing(worker.root, team.WORKER, "ecobuild")).split("## あなたの役：作業役")[1]
    assert "この仕事は報告だけです" in role_part and "task submit` で提出します" not in role_part
    assert team.PROGRESS_FILE in role_part and "task finish`・`workspace close` は使いません" in role_part
    assert "管理役" in role_part and "進行役" not in role_part
    assert team.PROGRESS_FILE in team.RESTART_PROMPT[team.WORKER]
    normal = Module.find(team.create(lead, "画面", "目的：作る").path)
    assert "task submit` で提出します" in "\n".join(team.briefing(normal.root, team.WORKER, "ecobuild"))
    assert failure(lambda: team.create(lead, "管理", "x", role=team.MANAGER, report_only=True)).code \
        == ErrorCode.INVALID_ARGUMENT


def test_the_worker_knows_its_lead_and_is_told_so_by_team_list(lead, monkeypatch):
    member = team.create(lead, "画面", "目的：作る")
    info = team.member_info(member.path)
    lead_task = lead.require_task_branch("x")
    assert info["lead_task"] == lead_task.number and info["lead_branch"] == lead_task.branch
    assert info["lead_role"] == team.MANAGER and info["lead_readable"] is False
    monkeypatch.chdir(member.path)
    doc = json.loads(CliRunner().invoke(build_cli(), ["agent", "team", "list", "--json"], catch_exceptions=False).stdout)
    assert not doc["ok"] and doc["error"]["message"].startswith(f"あなたは作業役です（管理役：「{lead.root.name}」・子タスク #")


def test_the_worker_reports_to_its_lead(lead, cli, monkeypatch):
    member = team.create(lead, "調べ", "目的：調べる", report_only=True)
    monkeypatch.chdir(member.path)
    runner = CliRunner()
    report = lambda: json.loads(runner.invoke(build_cli(), ["agent", "report", "--json"], catch_exceptions=False).stdout)
    assert not report()["ok"]                                                            # 報告がない
    (member.path / team.REPORT_FILE).write_text("結論：A がよい\n", encoding="utf-8")
    done = report()
    assert done["ok"] and done["result"]["report"].endswith(team.REPORT_FILE)
    monkeypatch.chdir(lead.root)
    listed = cli("agent", "team", "list")["result"]["members"][0]
    assert listed["report_told"] and listed["report_read"] is False                     # まだ届いていない
    got = agent_status.take(team.inbox_of(lead.root))
    assert "「調べ」" in got["text"] and "結論：A がよい" in got["text"] and got["kind"] == team.REPORT_KIND
    assert cli("agent", "team", "list")["result"]["members"][0]["report_read"] is True


def test_the_serve_runs_the_report_request(lead):
    member = team.create(lead, "調べ", "目的：調べる")
    ran = []
    serve = agent_serve.Serve(lambda args, cwd, **_: ran.append((args, cwd)) or {"ok": True, "result": {}})
    assert serve.handle(member.path, {"id": "r", "args": ["agent", "report", "--json"], "cwd": "."})["ok"]
    assert ran == [(["agent", "report", "--json"], member.path.resolve())]


# ---- 22：係が止まっているとき --------------------------------------------------------------------------------

def test_a_stopped_serve_is_found_at_once(lead, cli, monkeypatch):
    monkeypatch.setenv(team.WINDOW_VARIABLE, "1")
    team.create(lead, "画面", "目的：作る")
    folder = team.requests_folder(lead.root)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / team.SERVE_BEAT).write_text(json.dumps({"at": time.time() - 600}), encoding="utf-8")
    started = time.monotonic()
    error = failure(lambda: team.forward(lead.root, ["agent", "team", "send", "画面", "x"], lead.root))
    assert time.monotonic() - started < 2 and "止まっています" in error.message
    assert not list(folder.glob("*.json"))                                               # 頼みを置かない
    listed = cli("agent", "team", "list")                                                # 一覧は手元の記録から
    assert listed["ok"] and [m["name"] for m in listed["result"]["members"]] == ["画面"]
    assert "分かりません" in listed["result"]["note"]


def test_the_serve_leaves_a_sign_that_it_is_alive(lead):
    folder = agent_status.prepare(container.name(lead.root), lead.root)
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}})
    serve.step()
    beat = agent_status.read(folder / team.REQUESTS / team.SERVE_BEAT)
    assert beat and time.time() - beat["at"] < 5
