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


def test_the_list_shows_what_the_serve_saw_and_the_messages(lead, cli):
    member = team.create(lead, "画面", "目的：画面")
    (member.path / "x.txt").write_text("x\n", encoding="utf-8")
    team.lead_notice(member.path, "状態：続ける")                                        # 係が返答の終わりに調べる
    listed = cli("agent", "team", "list")["result"]["members"][0]
    assert listed["dirty"] == ["x.txt"] and listed["ahead"] == 0 and listed["submission"] is None
    assert listed["messages"] == [] and listed["replies"] == 0 and listed["report_at"] is None
