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
    from ecowork import github as ecowork_github
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    github = FakeGitHub(tmp_path / "gh")
    monkeypatch.setattr(ecowork_github, "default", lambda: github)   # 係が開く作業空間（作業役）も偽の GitHub に
    module = Module.create("Plain", directory=tmp_path, type="generic", github=github)
    module.repository.create_task("大きな仕事").start(name="大きな仕事")
    (module.root / team.MEMBER_FILE).parent.mkdir(parents=True, exist_ok=True)
    (module.root / team.MEMBER_FILE).write_text(json.dumps({"role": team.MANAGER}), encoding="utf-8")   # 作業役を作れる役
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
    assert team.role_of(worker.root) == team.WORKER and team.role_of(lead.root) == team.MANAGER
    assert team.agent_options(worker.root, team.WORKER, ("claude",)) == ("claude", "--model", "haiku")   # このPCの設定
    assert code_of(lambda: team.create(worker, "もっと", "分ける")) == ErrorCode.INVALID_ARGUMENT        # 作業役は作らない
    briefing = worker.agent_briefing(worker.require_task_branch("x"), team.WORKER)
    assert "作業役" in briefing and team.REPORT_FILE in briefing
    assert "提出しない" in briefing                                                   # レビュー・調べものは報告だけ
    assert "`状態：完了／質問あり／止まっている／続ける`" in briefing                       # 返答の最後の状態の行
    assert all(word in briefing for word in ("結果を待っています", "Edit・Write", "cat >>", "task submit", "「質問あり」", "（最後の規則）"))

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
    (lead.root / team.MEMBER_FILE).unlink()                                               # 記録のないトップ＝進行役
    sub = team.create(lead, "管理", "この部分を受け持つ", role=team.MANAGER, model="sonnet")
    assert team.role_of(sub.path) == team.MANAGER and sub.prompt == team.FIRST_PROMPT[team.MANAGER]
    assert team.agent_options(sub.path, team.MANAGER, ("claude",))[:3] == ("claude", "--model", "sonnet")   # 作ったときの指定
    ecobuild_bundle.set_config("agent_manager_model", "haiku")
    assert team.agent_options(lead.root, team.MANAGER, ("claude",)) == ("claude", "--model", "haiku")
    lead._status_settings(tmp_path, False, app=True, role=team.MANAGER)                       # 管理役も編集は .ecobuild/ai だけ
    assert "PreToolUse" in json.loads((tmp_path / agent_status.SETTINGS).read_text(encoding="utf-8"))["hooks"]
    program = lead.agent_briefing(lead.require_task_branch("x"), team.LEAD)
    assert "進行役" in program and "--manager" in program and team.PLAN_FILE in program
    assert "ユーザーとのやりとりに特化" in program and "作業役は直接作りません" in program and "--brief-file" not in program
    manager = Module.find(sub.path).agent_briefing(Module.find(sub.path).require_task_branch("x"), team.MANAGER)
    assert "管理役" in manager and "agent team start" in manager and "状態：" in manager and "send lead" in manager
    assert "### 手" in manager and "2〜3人" not in manager                                   # 人数は大きさ・独立さで
    assert all(word in manager for word in ("レビュー", "アイデア", "task close", "あなたに届きます"))
    assert "`## 持ち場`" in manager and "「注意なし」" in manager and "--lead" not in manager and "下の進行役" not in manager
    assert all(word in manager for word in ("自分では調べも作業もしません", "最初の動き", "観点を変えて", "接点", "workspace create",
                                            "task new", "進行役に聞くこと", "「不明」（状態の行がない）", "task diff",
                                            "task finish", "team close", "見えるのは", "task comment", "最初の1人を待たずに"))   # 管理役の決まり
    assert "状態：" in team.FIRST_PROMPT[team.WORKER] and "自分では調べずに" in team.FIRST_PROMPT[team.MANAGER]
    assert "前面" in team.FIRST_PROMPT[team.WORKER] and "task status" in team.RESTART_PROMPT[team.WORKER]
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
    assert got["text"].endswith("ボタンは右に") and got["text"].startswith("[管理役「")
    assert agent_status.take(team.inbox_of(member.path)) is None                       # 取り出したら空
    assert code_of(lambda: team.send(lead.root, "画面", " ")) == ErrorCode.INVALID_ARGUMENT

    where, text = team.lead_notice(member.path, "できました\n  確かめました")
    assert where == lead.root and "作業役「画面」" in text and "まだありません" in text
    assert text.endswith("最後の返答：できました 確かめました")
    (member.path / team.REPORT_FILE).write_text("できた\n", encoding="utf-8")
    assert f"報告：{team.TEAM_AREA}/{member.path.name}/{team.REPORT_FILE}" in team.lead_notice(member.path, "")[1]
    assert team.lead_notice(lead.root, "x") is None                                     # 進行役自身は知らせない


AREA_BRIEF = "目的：画面を作る\n\n## 持ち場\n- `src/ui/`\n- docs/ui.md（画面の説明）\n\n## 触らない\n- src/ui/old.py\n"


def worker_of(lead, brief=AREA_BRIEF):
    member = team.create(lead, "画面", brief)
    return member, Module.find(member.path, github=lead.repository.github)


def commit(worker, path, text="x\n"):
    file = worker.root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
    task_branch = worker.require_task_branch("x")
    task_branch.stage(path)
    task_branch.commit(f"{path} を変える")


def notice_of(member, message):
    """知らせの文：(注意の行, 事実の行)。"""
    lines = team.lead_notice(member.path, message)[1].splitlines()
    return lines[0], lines[1]


def test_the_notice_puts_cautions_first(lead):
    """係が作業空間・GitHub を調べ、作業役の言う状態と食い違うもの・注意を知らせの先頭に書く（注意がなければそう書く）。"""
    member, worker = worker_of(lead)
    commit(worker, "src/ui/login.py")
    (member.path / team.REPORT_FILE).write_text("できた\n", encoding="utf-8")
    first, facts = notice_of(member, "作りました。\n\n状態：完了")
    assert first.endswith("「画面」の返答が終わりました。注意：完了と言っていますが、提出がありません／"
                          "push していないコミットが 1 件あります")
    assert facts.startswith("状態：完了。報告：") and "提出：なし" in facts and "変えたファイル 1。" in facts

    pr = worker.submit()                                                                 # check を通して提出
    first, facts = notice_of(member, "提出しました。\n**状態：完了**")
    assert first.endswith("注意なし")
    assert f"提出：PR #{pr.number}（開いている・check を通した）" in facts

    commit(worker, "src/ui/more.py")
    worker.require_task_branch("x").push()                                               # check の後に push だけした
    assert "check を通した版の後のコミットが提出に入っています" in notice_of(member, "状態：完了")[0]
    worker.submit(check=False)
    first, facts = notice_of(member, "状態：完了")
    assert "--no-check で提出しました" in first and "・--no-check）" in facts


def test_the_notice_tells_changes_outside_the_area(lead):
    member, worker = worker_of(lead)
    commit(worker, "src/core.py")
    commit(worker, "src/ui/old.py")
    commit(worker, "docs/ui.md")
    (member.path / "src" / "ui" / "draft.py").write_text("まだ\n", encoding="utf-8")   # 未コミットの新しいファイル
    first, _ = notice_of(member, "状態：続ける")
    assert "持ち場の外のファイルを変えました（src/core.py）" in first
    assert "触らないはずのファイルを変えました（src/ui/old.py）" in first
    assert "未コミットの変更があります（src/ui/draft.py）" in first
    assert "完了と言って" not in first                                                  # 続ける：提出がなくてよい


def test_the_notice_without_a_state_line_or_an_area(lead):
    member, worker = worker_of(lead, "目的：画面を作る\n範囲：src/ui だけ")               # 持ち場の節がない：照らさない
    commit(worker, "src/core.py")
    first, facts = notice_of(member, "途中です")
    assert first.endswith("注意：返答の最後に状態の行がありません（作業中なら途中の区切り：待つ。待機中で変化がなければ send で状態の行を頼む。テスト待ちで返答を終えて止まった可能性もあります）／push していないコミットが 1 件あります")
    assert facts.startswith("状態：不明。") and "変えたファイル 1（持ち場は照らしていません）" in facts
    first, _ = notice_of(member, "状態：質問あり")
    assert "質問があります" in first


def test_a_report_only_worker_need_not_submit(lead):
    """任された仕事に「提出しない」とあれば（レビュー・調べもの）、完了で提出がなくても注意にしない。"""
    member, _ = worker_of(lead, "目的：PR #3 を読んで指摘を報告に書く。コードは変えない。**提出しない**")
    (member.path / team.REPORT_FILE).write_text("指摘\n", encoding="utf-8")
    assert notice_of(member, "状態：完了")[0].endswith("注意なし")


def test_the_notice_says_what_could_not_be_checked(lead, monkeypatch):
    member, _ = worker_of(lead)
    def broken(repo, head):
        raise WorkError("gh_error", "HTTP 502")
    monkeypatch.setattr(lead.repository.github, "pull_requests_for_branch", broken)
    first, _ = notice_of(member, "状態：完了")
    assert "調べられませんでした：提出（HTTP 502）" in first and "提出がありません" not in first   # 知らせは出す


def test_reading_the_state_line_and_the_area():
    assert team.reported_state("状態：続ける\n…\n> 状態: 完了") == team.DONE           # 最後の行
    assert team.reported_state("状態はよいです") == team.UNKNOWN_STATE
    assert team.brief_area("# 任せる\n## 持ち場\n- `src/a/`（画面）\n* src/b.py：説明\n1. tests/*.py\n"
                           "## 返してほしいもの\n- 報告\n### 触らない\n- src/c\n") \
        == (("src/a/", "src/b.py", "tests/*.py"), ("src/c",))
    assert team.brief_area("範囲：src だけ") == ((), ())


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
    """係：頼みを実行して結果を書き戻し、作業役の返答の終わりを進行役に知らせる。AI が起動する作業役はタブにしない
    （GUI に agent-start を出さない。起動は係がアプリ用で：tests/local/test_agent_app.py）。"""
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
    assert result("a")["ok"] and not events                                             # タブを開いてもらわない
    assert "起動していません" in result("a")["result"]["note"]                           # この係は起動できない（launch なし）
    assert not result("b")["ok"] and not result("c")["ok"]                             # チームの操作だけ・作業空間の中だけ
    assert [a for a, _ in ran] == [["agent", "team", "start", "画面", "--json"]]
    assert not list(requests.glob("*.taken"))

    (requests / "d.json").write_text(json.dumps({"id": "d", "args": ["agent", "team", "close", "画面"], "cwd": "."}),
                                     encoding="utf-8")
    serve.step()
    serve.wait()
    assert events[0]["event"] == "agent-stop" and events[0]["path"] == str(member.path)   # 人の画面のものは止めてもらう
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


def test_the_agent_always_starts_in_a_container(lead, monkeypatch):
    """エージェントはコンテナで動かす：コンテナでない作業空間は、起動の前に自動で container on にする（AI の起動も人の起動も）。"""
    from ecobuild_agent import inside
    seen = []
    monkeypatch.setattr(inside, "agent_launch", lambda root, agent, **options: (seen.append(agent) or ["x"], {}))
    monkeypatch.setattr(inside, "start_agent", lambda root, agent, **options: seen.append(agent) or type(
        "S", (), {"pid": 1, "command": agent, "directory": root})())
    assert not container.enabled(lead.root)
    lead.app_launch()
    assert container.enabled(lead.root) and seen                                          # AI が起動するもの
    from ecobuild import config
    config.save_local(lead.root, {})
    assert not container.enabled(lead.root)
    lead.start_agent(("claude",))
    assert container.enabled(lead.root) and len(seen) == 2                                # 人が起動するもの


def test_the_manager_is_the_only_one_under_the_lead_and_makes_the_workers(lead):
    """記録のない作業空間は進行役：管理役を1人だけ作り（作業役は直接作れない）、作業役の知らせは作った管理役に届く
    （進行役には届かない）。管理役は上の役へ send できる。"""
    top = Path(lead.root)
    (top / team.MEMBER_FILE).unlink()                                                      # 記録のないトップ
    assert team.role_of(top) == team.LEAD
    assert code_of(lambda: team.create(lead, "画面", "直接", role=team.WORKER)) == ErrorCode.INVALID_ARGUMENT
    manager = team.create(lead, "管理", "ユーザーの依頼：画面を作る", role=team.MANAGER)
    assert manager.role == team.MANAGER and team.team(lead.root).members[0].role == team.MANAGER
    assert code_of(lambda: team.create(lead, "管理2", "もう1人", role=team.MANAGER)) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: team.create(lead, "進行", "x", role=team.LEAD)) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: team.create(lead, "x", "y", role="boss")) == ErrorCode.INVALID_ARGUMENT
    manager_module = Module.find(manager.path)
    assert team.role_of(manager.path) == team.MANAGER
    assert code_of(lambda: team.create(manager_module, "孫", "x", role=team.MANAGER)) == ErrorCode.INVALID_ARGUMENT
    worker = team.create(manager_module, "画面", "目的：画面を作る", role=team.WORKER)    # 作業役は管理役の下に
    assert [m.name for m in team.team(manager.path).members] == ["画面"] and [m.name for m in team.team(top).members] == ["管理"]
    where, notice = team.lead_notice(worker.path, "できました\n状態：完了")
    assert where == manager.path and where != top and "作業役「画面」" in notice             # 知らせの宛先は管理役
    team.send(top, "管理", "ボタンは右に")                                                  # 進行役 → 管理役
    got = agent_status.take(team.inbox_of(manager.path))
    assert got["text"].startswith("[進行役「") and got["text"].endswith("ボタンは右に")
    team.send(manager.path, "lead", "画面を取り込みました")                                 # 管理役 → 進行役
    up = agent_status.take(team.inbox_of(top))
    assert up["text"].startswith("[管理役「管理」から]") and up["text"].endswith("取り込みました")
    assert agent_status.take(team.inbox_of(top)) is None                                  # 作業役の知らせは進行役の受け箱に入らない
    where, text = team.lead_notice(manager.path, "終わりました\n状態：完了")               # 管理役の返答の終わり → 進行役
    assert where == top and text.startswith("[ECOBUILD]".replace("ECOBUILD", "ECOBuild") + " 管理役「管理」の返答が終わりました")


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
    assert lead._role("", ("claude", "--resume", "other"), False, None, None) == team.MANAGER   # 知らない会話：作業空間の記録
    assert lead._role("", ("claude", "--resume"), False, None, None) == team.MANAGER          # Claude の一覧で選ぶ：分からない
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
    assert result["ok"] and result["result"]["args"][-1] == "--no-open"                # 起動は係が（アプリ用で）
    assert [e["event"] for e in events] == ["agent-stop"]                              # タブを開いてもらわない
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


# ---- 並べて作る・作りかけの片付け ------------------------------------------------------------------------------

def slow_clone(monkeypatch, seconds):
    """clone を遅くする（本物の clone は数十秒かかる。並べて実行されているかを時間で確かめる）。"""
    import ecowork.git
    real = ecowork.git.clone

    def clone(url, destination, **options):
        time.sleep(seconds)
        return real(url, destination, **options)
    monkeypatch.setattr(ecowork.git, "clone", clone)


def create_side_by_side(lead, names):
    """names の作業役を、別々のコマンドのように（それぞれの Module で）同時に作る。(作った人, 失敗) を返す。"""
    made, errors = [], []

    def one(name):
        try:
            made.append(team.create(Module.find(lead.root, github=lead.repository.github), name, f"目的：{name}を作る"))
        except Exception as error:
            errors.append(error)
    threads = [threading.Thread(target=one, args=(name,)) for name in names]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(120)
    return made, errors


def test_workers_can_be_created_side_by_side(lead, monkeypatch):
    """5人を同時に作っても、git の除外・作業空間の記録を壊さず、全員そろう時間は1人分の数倍以内。"""
    slow_clone(monkeypatch, 2.0)
    started = time.monotonic()
    team.create(lead, "最初", "目的：1人分の時間を測る")
    one = time.monotonic() - started
    exclude = lead.root / ".git" / "info" / "exclude"
    before = exclude.read_text(encoding="utf-8")

    started = time.monotonic()
    made, errors = create_side_by_side(lead, ["画面", "保存", "検索", "印刷", "設定"])
    took = time.monotonic() - started
    assert errors == [] and len(made) == 5
    assert took < one * 3, (took, one)                                                       # 1人ずつなら 5 倍
    assert len({member.task for member in made}) == 5
    assert sorted(m.name for m in team.team(lead.root).members) == sorted(["最初", "画面", "保存", "検索", "印刷", "設定"])
    for member in made:                                                                       # 記録が消えていない
        assert any(workspaces.same(item.path, member.path) for item in workspaces.recorded())
    assert exclude.read_text(encoding="utf-8") == before and lead.repository.git.working_tree().untracked == ()


def test_the_exclude_is_written_once_when_many_add_to_it_at_once(lead):
    """git の除外（info/exclude）に同時に書き足しても、元の行を消さず、1回だけ足す。"""
    exclude = lead.root / ".git" / "info" / "exclude"
    exclude.write_text("# 人が書いた行\n*.log\n", encoding="utf-8")
    modules = [Module.find(lead.root, github=lead.repository.github) for _ in range(8)]
    threads = [threading.Thread(target=module.prepare_agent_area) for module in modules]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    lines = exclude.read_text(encoding="utf-8").splitlines()
    assert lines[:2] == ["# 人が書いた行", "*.log"] and lines.count("/.ecobuild/ai/") == 1


def test_the_same_name_is_not_created_twice(lead):
    member = team.create(lead, "画面", "目的：作る")
    assert code_of(lambda: team.create(lead, "画面", "目的：もう一度")) == ErrorCode.ALREADY_EXISTS   # もういる
    with team._creating(lead, "保存"):                                                        # 別の頼みが作っている途中
        assert code_of(lambda: team.create(Module.find(lead.root, github=lead.repository.github), "保存", "目的：作る")) \
            == ErrorCode.ALREADY_EXISTS
    assert [m.task for m in team.team(lead.root).members] == [member.task]
    assert team.create(lead, "保存", "目的：作る").name == "保存"                               # 終われば作れる


def remote_branches(lead):
    bare = lead.repository.github.bare
    return subprocess.run(["git", "-C", str(bare), "branch", "--list", "task/*"], capture_output=True, text=True,
                          encoding="utf-8").stdout.split()


def test_a_failed_creation_cleans_up_what_it_made(lead, monkeypatch):
    """作成の途中（clone とタスクブランチの push の後）で失敗したら、作業空間を消し、ブランチを消し、子タスクを閉じて、
    失敗の文にそう書く。"""
    from ecowork.git import Git
    from ecowork import WorkError as Failure
    real = Git.set_config

    def broken(self, key, value):
        if self.root != lead.root:
            raise Failure("github_error", "GitHub に断られました：HTTP 502 Bad Gateway")
        return real(self, key, value)
    monkeypatch.setattr(Git, "set_config", broken)
    before = set(remote_branches(lead))
    with pytest.raises(WorkError) as caught:
        team.create(lead, "グラフ", "目的：グラフを作る")
    github = lead.repository.github
    child = max(github.issues)
    assert github.issues[child].title == "グラフ" and github.issues[child].state == "closed" and child in github.not_planned
    assert "作成が途中で失敗" in github.comments[child][-1].body                               # 理由を書いて閉じる
    assert not list((lead.root / team.TEAM_AREA).glob("*"))                                    # 作業空間は残らない
    assert set(remote_branches(lead)) == before                                                # この回に置いたブランチも
    error = caught.value
    assert "「グラフ」を作れませんでした" in error.message and "HTTP 502" in error.message
    assert f"子タスク #{child} は閉じ" in error.hint and error.code == "github_error"

    monkeypatch.setattr(Git, "set_config", real)
    member = team.create(lead, "グラフ", "目的：グラフを作る")                                 # 作り直せる（新しい子タスク）
    assert member.task != child


def test_a_failure_after_making_the_child_task_closes_it(lead, monkeypatch):
    """子タスクを作った後の読み直しで失敗しても（作ったものの番号が返らない）、親の子から見つけて閉じる。"""
    from ecotask.tracker import Tracker
    from ecowork import WorkError as Failure

    def broken(self, number):
        raise Failure("github_error", "HTTP 502")
    monkeypatch.setattr(Tracker, "issue", broken)
    with pytest.raises(WorkError) as caught:
        team.create(lead, "グラフ", "目的：作る")
    child = max(lead.repository.github.issues)
    assert lead.repository.github.issues[child].state == "closed" and f"#{child} は閉じ" in caught.value.hint


def test_a_creation_that_stopped_halfway_is_continued(lead):
    """前に作りかけて止まったもの（係が止めた等：開いた子タスクと、記録のないフォルダー）があれば、片付けて続きから作る。"""
    github = lead.repository.github
    parent = lead.require_task_branch("x").number
    left = lead.repository.create_task("グラフ", body="目的：作る", parent=parent)
    folder = lead.root / team.TEAM_AREA / f"{left.number}-グラフ"
    folder.mkdir(parents=True)
    (folder / "途中.txt").write_text("clone の途中\n", encoding="utf-8")
    issues = len(github.issues)
    member = team.create(lead, "グラフ", "目的：作る")
    assert member.task == left.number and member.path == folder and len(github.issues) == issues   # 二重にしない
    assert not (folder / "途中.txt").exists()


def test_a_leftover_with_changes_is_not_removed(lead):
    """記録のない作りかけのフォルダーでも、中に変更があれば消さずに止める。"""
    member = team.create(lead, "グラフ", "目的：作る")
    (member.path / team.MEMBER_FILE).unlink()                                                 # できあがる前に止まった形
    (member.path / "変更.txt").write_text("人の変更\n", encoding="utf-8")
    assert code_of(lambda: team.create(lead, "グラフ", "目的：作る")) == ErrorCode.ALREADY_EXISTS
    assert (member.path / "変更.txt").exists()


def test_the_serve_creates_workers_side_by_side_but_keeps_other_requests_in_order(lead):
    """同じ置き場所の作業役の作成どうしは START_LIMIT まで並べる。ほかの頼み（close 等）は前の作成が終わってから、
    後の作成はその頼みが終わってから。"""
    folder = agent_status.prepare(container.name(lead.root), lead.root)
    requests = folder / team.REQUESTS
    requests.mkdir()
    guard, running, most, order = threading.Lock(), [0], [0], []

    def run(args, cwd, **_):
        with guard:
            running[0] += 1
            most[0] = max(most[0], running[0])
            order.append(("始", args[2], args[3]))
        time.sleep(0.3)
        with guard:
            running[0] -= 1
            order.append(("終", args[2], args[3]))
        return {"ok": True, "result": {}}

    serve = agent_serve.Serve(run, emit=lambda event: None)
    plan = [("a", "start", "1"), ("b", "start", "2"), ("c", "start", "3"), ("d", "start", "4"), ("e", "start", "5"),
            ("f", "list", "x"), ("g", "start", "6")]
    for key, command, name in plan:
        (requests / f"{key}.json").write_text(json.dumps({"id": key, "args": ["agent", "team", command, name], "cwd": "."}),
                                              encoding="utf-8")
    started = time.monotonic()
    serve.step()
    assert serve.wait(30)
    assert most[0] == agent_serve.START_LIMIT                                                  # 4人ずつ並べる
    assert time.monotonic() - started < 0.3 * 7 * 0.8                                         # 1つずつより早い
    position = {entry: index for index, entry in enumerate(order)}
    ended_starts = [position[("終", "start", n)] for n in "12345"]
    assert position[("始", "list", "x")] > max(ended_starts)                                  # 前の作成が終わってから
    assert position[("始", "start", "6")] > position[("終", "list", "x")]                     # 後の作成はその後
    assert all((requests / f"{key}.result.json").exists() for key, _, _ in plan)


def test_two_conversations_in_one_workspace_do_not_mix(lead, monkeypatch):
    """同じ作業空間の会話が2つ：作業役の一覧・言付け・返答の知らせは、作った会話の分だけ。"""
    monkeypatch.setenv(team.OWNER_VARIABLE, "session-a")
    first = team.create(lead, "甲", "目的：甲")
    monkeypatch.setenv(team.OWNER_VARIABLE, "session-b")
    second = team.create(lead, "乙", "目的：乙")
    assert [m.name for m in team.team(lead.root, "session-a").members] == ["甲"]
    assert [m.name for m in team.team(lead.root, "session-b").members] == ["乙"]
    assert len(team.team(lead.root).members) == 2                                       # 区別しなければ全員（係）
    assert code_of(lambda: team.send(lead.root, "甲", "x")) == ErrorCode.INVALID_ARGUMENT   # 会話 b からは甲が見えない
    team.send(lead.root, "乙", "y")
    monkeypatch.setenv(team.OWNER_VARIABLE, "")                                         # 会話が分からなければ区別しない
    assert len(team.team(lead.root, team.owner_session()).members) == 2

    folder = team.inbox_of(lead.root)
    agent_status.put(folder, "甲の知らせ", owner=team.notice_owner(first.path))
    agent_status.put(folder, "乙の知らせ", owner=team.notice_owner(second.path))
    assert agent_status.take(folder, "session-b")["text"] == "乙の知らせ"
    assert agent_status.take(folder, "session-b") is None                               # 甲の知らせは取らない
    assert agent_status.take(folder, "session-a")["text"] == "甲の知らせ"
