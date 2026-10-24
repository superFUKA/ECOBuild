"""子のエージェント（ecobuild_agent.children と係のツール）：直接の子だけ・起動してよい登録・子の数の上限・手伝いと子タスク・
言付け・親への知らせ・閉じる・取り込む。頼みは MCP のツールから係へ（requests/）。

本物の Claude Code の代わりに、偽の claude（FAKE：標準入力の発言を記録して、返答の終わりを出す）で確かめる。
"""

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from fakes import FakeGitHub
from ecobuild.errors import EcoBuildError
from ecobuild_agent import agents, app, children, mcp, registry
from ecobuild_agent import serve as agent_serve
from ecobuild_agent import status as agent_status
from ecobuild_agent.errors import ErrorCode
from ecobuild_bundle import Module
from ecowork import WorkError

pytestmark = pytest.mark.local

FAKE = r'''
import io, json, sys
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
record, args = sys.argv[1], sys.argv[2:]
session = args[args.index("--session-id") + 1] if "--session-id" in args else args[args.index("--resume") + 1]
def out(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False) + "\n")
    sys.stdout.flush()
out({"type": "system", "subtype": "init", "session_id": session, "model": "fake-model"})
for line in sys.stdin:
    text = json.loads(line)["message"]["content"]
    with open(record, "a", encoding="utf-8") as f:
        f.write(json.dumps({"got": text}, ensure_ascii=False) + "\n")
    out({"type": "result", "subtype": "success", "is_error": False, "result": "了解。\n状態：続ける", "session_id": session})
'''


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
        agents.update(agent_id, session=session)
        folder = agent_status.prepare(record.folder, record.root)
        argv = (sys.executable, str(self.script), str(self.record),
                *(("--resume", resume) if resume else ("--session-id", session)))
        return app.Launch(record.root, folder, argv, None, session, agent_id, record.registration)

    def got(self) -> list[str]:
        if not self.record.is_file():
            return []
        return [x["got"] for x in map(json.loads, self.record.read_text(encoding="utf-8").splitlines()) if "got" in x]


def until(check, seconds=30.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return
        time.sleep(0.05)
    pytest.fail("待ちきれませんでした")


@pytest.fixture
def lead(tmp_path, monkeypatch):
    from ecowork import github as ecowork_github
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    github = FakeGitHub(tmp_path / "gh")
    monkeypatch.setattr(ecowork_github, "default", lambda: github)   # 係が開く作業空間（子タスク）も偽の GitHub に
    module = Module.create("Plain", directory=tmp_path, type="generic", github=github)
    module.repository.create_task("大きな仕事").start(name="大きな仕事")
    return module


@pytest.fixture
def parent(lead):
    """lead の作業空間の、管理役の登録のエージェント（子を起動できる）。"""
    task = lead.require_task_branch("x")
    record = agents.create(registration="manager", workspace=lead.root, task={"number": task.number, "branch": task.branch})
    agent_status.prepare(record.folder, lead.root)
    return record


@pytest.fixture
def serve(lead, tmp_path):
    fake = Fake(tmp_path)
    found = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake,
                              find=lambda path: Module.find(path, github=lead.repository.github), background=False)
    found.fake = fake
    yield found
    for agent in found.apps.agents():
        found.apps.stop(agent.agent_id, 5)


def call(serve, caller, tool, **arguments):
    """caller の置き場所からのツールの頼み（係がその場で実行する）。"""
    return serve.handle(caller.root, {"id": "x", "tool": tool, "arguments": arguments, "agent": caller.id},
                        folder=caller.folder)


def idle(serve, child):
    """子が返答を終えて待機中になるまで、係に出来事を読ませる。"""
    until(lambda: serve.apps.step() is not None and agent_status.activity(child.folder)["state"] == agent_status.IDLE)


def ok(doc):
    assert doc["ok"], doc
    return doc["result"]


def helper_of(serve, parent, brief="目的：README を読んで要点を報告する", **extra):
    return agents.load(ok(call(serve, parent, "children_start", registration="worker", kind="helper", brief=brief,
                                **extra))["id"])


def test_a_helper_works_in_the_parents_workspace_without_a_task_of_its_own(serve, parent):
    result = ok(call(serve, parent, "children_start", registration="worker", kind="helper", brief="目的：調べる",
                     title="調べ係"))
    child = agents.load(result["id"])
    assert result["app"] and child.parent == parent.id and child.kind == agents.HELPER and child.name == "調べ係"
    assert child.root == parent.root and child.task == parent.task                       # 同じ作業空間・親のタスク
    assert serve.fake.launched[-1]["id"] == child.id
    until(lambda: serve.fake.got())
    assert "あなたは手伝いです" in serve.fake.got()[0] and serve.fake.got()[0].endswith("目的：調べる")
    assert (child.folder / children.BRIEF_COPY).read_text(encoding="utf-8") == "目的：調べる\n"
    listed = ok(call(serve, parent, "children_list"))["members"]
    assert [m["id"] for m in listed] == [child.id] and listed[0]["kind"] == agents.HELPER
    assert listed[0]["registration"] == "worker" and "state" in listed[0] and listed[0]["messages"] == []
    named = helper_of(serve, parent)
    assert named.name == "worker-2"                                                      # 名前を省けば <登録>-<番号>


def test_only_direct_children_can_be_handled(serve, parent, lead):
    child = helper_of(serve, parent)
    grandchild = agents.create(registration="worker", workspace=lead.root, parent=child.id, kind=agents.HELPER)
    other = agents.create(registration="manager", workspace=lead.root)
    stranger = agents.create(registration="worker", workspace=lead.root, parent=other.id, kind=agents.HELPER)
    for target in (grandchild, stranger, other, parent):
        refused = call(serve, parent, "children_send", id=target.id, text="やあ")
        assert not refused["ok"] and "直接の子ではありません" in refused["error"]["message"]
    assert ok(call(serve, parent, "children_send", id=child.id, text="やあ"))["message_id"]
    assert [m["id"] for m in ok(call(serve, parent, "children_list"))["members"]] == [child.id]   # 孫は出ない


def test_the_caller_is_the_folder_of_the_request_not_its_arguments(serve, parent, lead):
    other = agents.create(registration="manager", workspace=lead.root)
    doc = serve.handle(lead.root, {"id": "x", "tool": "children_list", "arguments": {}, "agent": other.id},
                       folder=parent.folder)
    assert not doc["ok"] and "頼んだエージェントが分かりません" in doc["error"]["message"]
    unknown = call(serve, parent, "children_list", id="a-0123456789")
    assert not unknown["ok"] and "知らない入力" in unknown["error"]["message"]          # 入力の形も係で確かめる


def test_the_number_of_children_is_limited(serve, parent):
    registry.update("manager", max_children=1)
    helper_of(serve, parent)
    refused = call(serve, parent, "children_start", registration="worker", kind="helper", brief="もう1人")
    assert not refused["ok"] and "上限（1）" in refused["error"]["message"]


def write_registration(name: str, *, tools: list[str], children_: list[str], max_children: int = 3) -> None:
    """確かめ（registry._check）を通さずに、ユーザーの登録を置く（手で書き換えた登録のような）。"""
    folder = registry.user_root() / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / registry.SETTINGS_FILE).write_text(
        f"title = \"{name}\"\nchildren = {json.dumps(children_)}\nmax_children = {max_children}\ntools = {json.dumps(tools)}\n",
        encoding="utf-8")


def test_only_allowed_and_not_stronger_registrations_are_started(serve, parent, lead):
    refused = call(serve, parent, "children_start", registration="lead", kind="helper", brief="進めて")
    assert not refused["ok"] and "起動してよい子ではありません" in refused["error"]["message"]
    assert "worker" in refused["error"]["hint"]
    write_registration("narrow", tools=["task_*", "children_*"], children_=["worker"])     # worker（tools *）は強い
    narrow = agents.create(registration="narrow", workspace=lead.root, parent=parent.id, kind=agents.HELPER)
    stronger = call(serve, narrow, "children_start", registration="worker", kind="helper", brief="調べて")
    assert not stronger["ok"] and "より強い" in stronger["error"]["message"]
    reported = call(serve, narrow, "report_to_parent", text="終わりました")              # 登録で許していないツール
    assert not reported["ok"] and "許されていません" in reported["error"]["message"]


def test_a_helper_does_not_make_child_tasks_or_accept(serve, parent):
    child = helper_of(serve, parent)
    refused = call(serve, child, "children_start", registration="worker", kind="subtask", brief="分ける")
    assert not refused["ok"] and "手伝いは子タスクを作れません" in refused["error"]["message"]
    accepted = call(serve, parent, "children_accept", id=child.id)
    assert not accepted["ok"] and "手伝いなので" in accepted["error"]["message"]


def test_send_cancel_and_report_to_the_parent(serve, parent):
    child = helper_of(serve, parent)
    serve.apps.stop(child.id, 5)                                                         # 受け箱に残す（係が届けない）
    sent = ok(call(serve, parent, "children_send", id=child.id, text="ボタンは右に"))
    got = agent_status.read(next((child.folder / agent_status.INBOX).glob("*.json")))
    assert got["text"] == f"[親「{parent.name}」（{parent.id}）から] ボタンは右に"
    assert ok(call(serve, parent, "children_cancel", id=child.id, message=sent["message_id"]))
    again = call(serve, parent, "children_cancel", id=child.id, message=sent["message_id"])
    assert not again["ok"] and "もう届いています" in again["error"]["message"]
    member = ok(call(serve, parent, "children_list"))["members"][0]
    assert member["messages"][0]["cancelled"] and member["report_told"] is None

    told = ok(call(serve, child, "report_to_parent", text="要点：3つあります"))
    notice = agent_status.take(parent.folder)
    assert "から知らせです" in notice["text"] and notice["text"].endswith("要点：3つあります")
    assert told["parent"] == parent.id and (child.folder / children.REPORT_COPY).is_file()
    member = ok(call(serve, parent, "children_list"))["members"][0]
    assert member["report_told"] and member["report_read"] and member["reported"]
    orphan = call(serve, parent, "report_to_parent", text="親は？")
    assert not orphan["ok"] and "親がいません" in orphan["error"]["message"]


def test_the_parent_is_told_when_a_helper_replies(serve, parent):
    child = helper_of(serve, parent)
    serve.replied(child.folder, "調べました。\n状態：質問あり")
    notice = agent_status.take(parent.folder)
    assert notice["kind"] == agent_status.NOTICE and notice["from"] == child.id
    assert "質問があります" in notice["text"] and "（手伝い：提出なし）" in notice["text"]
    assert notice["text"].endswith("最後の返答：調べました。 状態：質問あり")
    serve.replied(child.folder, "一つ目")
    serve.replied(child.folder, "二つ目\n状態：完了")
    texts = [item["text"] for item in iter(lambda: agent_status.take(parent.folder), None)]
    assert len(texts) == 1 and "注意なし" in texts[0] and "前の知らせ 1 件" in texts[0]   # まだ届いていないものはまとめる


def test_restarting_and_closing_a_helper(serve, parent):
    child = helper_of(serve, parent, brief="目的：調べる")
    idle(serve, child)
    restarted = ok(call(serve, parent, "children_restart", id=child.id, resume=True))
    assert restarted["resumed"] and serve.fake.launched[-1]["resume"] == "s-1"
    until(lambda: serve.fake.got()[-1:] == [children.RESUME_PROMPT])
    restarted = ok(call(serve, parent, "children_restart", id=child.id))
    assert not restarted["resumed"]
    until(lambda: "起動し直しました" in serve.fake.got()[-1] and serve.fake.got()[-1].endswith("目的：調べる"))
    log = ok(call(serve, parent, "children_log", id=child.id, tail=0))
    assert log["events"] and log["activity"]["mode"] == agent_status.APP
    idle(serve, child)

    closed = ok(call(serve, parent, "children_close", id=child.id))
    folder = f"{children.ARCHIVE}/{child.id}-{child.name}"
    assert closed["archive"] == [f"{folder}/{children.BRIEF_COPY}"] and (parent.root / folder / "brief.md").is_file()
    assert not serve.apps.holds(child.id) and child.id not in [a.id for a in agents.all_records()]
    assert parent.root.exists()                                                          # 手伝いの作業空間は親のもの


def test_closing_the_last_running_agent_stops_the_container(serve, parent, lead, monkeypatch):
    """作業空間の最後の（動いている）エージェントを閉じたら、その作業空間のコンテナを止める（動いたままだと
    ロックになり、task finish が止まる）。ほかのエージェントが動いていれば止めない。"""
    stopped = []
    monkeypatch.setattr(children, "stop_container", lambda root, progress=None: stopped.append(Path(root)))
    first, second = helper_of(serve, parent), helper_of(serve, parent)
    idle(serve, first)
    idle(serve, second)
    ok(call(serve, parent, "children_close", id=first.id))
    assert stopped == []                                                                 # second が動いている
    ok(call(serve, parent, "children_close", id=second.id))
    assert stopped == [lead.root]                                                        # parent は動いていない


def test_a_child_with_children_is_not_closed(serve, parent, lead):
    child = helper_of(serve, parent)
    agents.create(registration="worker", workspace=lead.root, parent=child.id, kind=agents.HELPER, name="孫")
    serve.apps.stop(child.id, 5)
    refused = call(serve, parent, "children_close", id=child.id)
    assert not refused["ok"] and refused["error"]["code"] == ErrorCode.UNFINISHED_WORK
    assert any("まだ子がいます" in d for d in refused["error"]["details"])


def commit(module, path, text="x\n"):
    file = module.root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
    task_branch = module.require_task_branch("x")
    task_branch.stage(path)
    task_branch.commit(f"{path} を変える")


@pytest.mark.needs_git_2_48
def test_a_subtask_is_a_child_task_in_its_own_workspace_and_is_accepted(serve, parent, lead):
    result = ok(call(serve, parent, "children_start", registration="worker", kind="subtask",
                     brief="目的：画面を作る\n\n## 持ち場\n- `src/ui/`\n", title="画面"))
    child = agents.load(result["id"])
    number = child.task["number"]
    assert child.kind == agents.OWNER and child.parent == parent.id and child.name == "画面"
    assert child.root == lead.workspace_place(str(number)) and child.task["branch"] == f"task/{number}-画面"
    assert [i.number for i in lead.repository.github.sub_issues(lead.root, parent.task["number"])] == [number]
    assert (child.root / children.BRIEF_FILE).read_text(encoding="utf-8").startswith("目的：画面を作る")
    until(lambda: serve.fake.got())
    assert serve.fake.got()[0] == registry.load("worker").first_prompt

    worker = Module.find(child.root, github=lead.repository.github)
    commit(worker, "src/ui/a.txt")
    commit(worker, "src/core.txt")
    where, text = children.parent_notice(child, "作りました\n状態：完了")
    assert where.id == parent.id and f"子「画面」（{child.id}・子タスク #{number}）" in text
    assert "完了と言っていますが、提出がありません" in text and "持ち場の外のファイルを変えました（src/core.txt）" in text
    worker.submit(check=False)
    idle(serve, child)
    accepted = ok(call(serve, parent, "children_accept", id=child.id))
    assert accepted["task"] == number and accepted["finish"]["task"] == number and "branch" in accepted["sync"]
    assert not child.root.exists() and (lead.root / "src" / "ui" / "a.txt").is_file()   # 取り込んで手元を最新に
    assert child.id not in [a.id for a in agents.all_records()] and not serve.apps.holds(child.id)
    assert (lead.root / children.ARCHIVE / f"{child.id}-画面" / "brief.md").is_file()


@pytest.mark.needs_git_2_48
def test_a_subtask_with_local_changes_is_not_closed(serve, parent, lead):
    child = agents.load(ok(call(serve, parent, "children_start", registration="worker", kind="subtask",
                                brief="目的：直す"))["id"])
    assert child.name == "worker-1" and lead.repository.task(child.task["number"]).title == "目的：直す"
    (child.root / "draft.txt").write_text("まだ\n", encoding="utf-8")
    idle(serve, child)
    refused = call(serve, parent, "children_close", id=child.id)
    assert not refused["ok"] and "GitHub にない変更" in refused["error"]["message"]
    assert refused["error"]["details"] == ["ファイル：draft.txt"] and child.root.exists()
    (child.root / "draft.txt").unlink()
    closed = ok(call(serve, parent, "children_close", id=child.id))
    assert closed["workspace"] and not child.root.exists()


def test_a_failed_subtask_closes_the_child_task(serve, parent, lead, monkeypatch):
    def broken(self, number, **_):
        raise WorkError(ErrorCode.AGENT_ERROR, "作れません")
    monkeypatch.setattr(Module, "start_task", broken)
    refused = call(serve, parent, "children_start", registration="worker", kind="subtask", brief="目的：作る",
                   title="壊れる")
    assert not refused["ok"] and "作れませんでした" in refused["error"]["message"]
    number = int(refused["error"]["details"][0].split("#")[1].split("（")[0])
    assert lead.repository.task(number).state == "closed" and not agents.children(parent.id)


def test_a_message_to_a_stopped_child_wakes_it(serve, parent):
    """止まっている子に言付けを送ると、前の会話の続きから起こして届ける（届けるのは動いている子だけなので）。"""
    child = helper_of(serve, parent)
    idle(serve, child)
    serve.apps.stop(child.id, 5)
    sent = ok(call(serve, parent, "children_send", id=child.id, text="ボタンは右に"))
    assert sent["woken"] and serve.fake.launched[-1] == {"root": child.root, "id": child.id, "resume": "s-1"}
    until(lambda: serve.apps.step() is not None
          and serve.fake.got()[-1:] == [f"[親「{parent.name}」（{parent.id}）から] ボタンは右に"])
    moving = ok(call(serve, parent, "children_send", id=child.id, text="もう一つ"))      # 動いている：起こさない
    assert "woken" not in moving and len(serve.fake.launched) == 2


def test_a_stopped_child_of_a_closed_task_is_not_woken_and_can_be_closed(serve, parent):
    """タスクが閉じていれば起こさず、わけと起こし方を結果に書く。止まっている子への届いていない言付けは、閉じるのを止めない。"""
    child = helper_of(serve, parent)
    idle(serve, child)
    serve.apps.stop(child.id, 5)
    serve.run = lambda args, cwd, **_: {"ok": True, "result": {"state": "closed"}}
    sent = ok(call(serve, parent, "children_send", id=child.id, text="ボタンは右に"))
    assert sent["woken"] is False and "タスクが閉じている" in sent["note"] and "children_restart" in sent["note"]
    assert len(serve.fake.launched) == 1 and agent_status.activity(child.folder)["waiting"] == 1
    assert ok(call(serve, parent, "children_close", id=child.id))


def test_a_child_is_starting_until_it_runs(serve, parent):
    """係が起動している間（コンテナの用意）は、止まっているではなく起動中。起動し直す途中も。失敗したら印を消す。"""
    seen = []
    launch = serve.apps.launch

    def watching(agent_id, resume, progress):
        seen.append(agent_status.activity(agents.load(agent_id).folder)["state"])
        return launch(agent_id, resume, progress)
    serve.apps.launch = watching
    child = helper_of(serve, parent)
    assert seen == [agent_status.STARTING]
    assert agent_status.activity(child.folder)["state"] in (agent_status.WORKING, agent_status.IDLE)
    idle(serve, child)
    ok(call(serve, parent, "children_restart", id=child.id))
    assert seen == [agent_status.STARTING] * 2

    def broken(agent_id, resume, progress):
        raise EcoBuildError(ErrorCode.AGENT_ERROR, "コンテナを用意できません")
    serve.apps.launch = broken
    failed = ok(call(serve, parent, "children_start", registration="worker", kind="helper", brief="もう1人"))
    assert "起動していません" in failed["note"]
    assert agent_status.activity(agents.load(failed["id"]).folder)["state"] == agent_status.STOPPED
    assert children.describe_activity({"state": agent_status.STARTING, "since": time.time() - 90}) == "起動中（1分）"


@pytest.mark.needs_git_2_48
def test_after_finish_the_child_is_forgotten_even_if_its_workspace_is_left(serve, parent, lead, monkeypatch):
    """取り込めた（task finish）後は、作業空間を閉じられなくても子の記録を閉じ、残したわけを note に書く。"""
    child = agents.load(ok(call(serve, parent, "children_start", registration="worker", kind="subtask",
                                brief="目的：直す"))["id"])
    idle(serve, child)
    monkeypatch.setattr(Module, "finish", lambda self, number, **_: {"task": number})

    def kept(cls, path, **_):
        raise EcoBuildError(ErrorCode.UNFINISHED_WORK, "GitHubにないものがあります。", details=["GitHubにないコミット 1 件"])
    monkeypatch.setattr(Module, "close_workspace", classmethod(kept))
    accepted = ok(call(serve, parent, "children_accept", id=child.id))
    assert child.id not in [a.id for a in agents.all_records()] and child.root.exists()
    assert "閉じられなかったので残しました" in accepted["note"] and "GitHubにないコミット 1 件" in accepted["note"]
    assert f'ecobuild workspace close "{child.root}" --discard-local' in accepted["note"]


@pytest.mark.needs_git_2_48
def test_a_subtask_whose_pull_request_was_merged_and_branch_deleted_is_closed(serve, parent, lead):
    """提出がスカッシュで取り込まれ、GitHub のタスクブランチが消えた後も、元のコミットを GitHub にないものとみなさない
    （マージ済みのPRに入っている）。"""
    child = agents.load(ok(call(serve, parent, "children_start", registration="worker", kind="subtask",
                                brief="目的：直す"))["id"])
    worker = Module.find(child.root, github=lead.repository.github)
    commit(worker, "a.txt")
    worker.submit(check=False)
    idle(serve, child)
    github = lead.repository.github
    pull = github.pull_requests_for_branch(child.root, child.task["branch"])[0]
    github.merge_pull_request(child.root, pull.number, squash=True, subject=None)
    worker.repository.git.run("push", "--quiet", "origin", "--delete", child.task["branch"])
    closed = ok(call(serve, parent, "children_close", id=child.id))
    assert closed["workspace"] and not child.root.exists()


@pytest.mark.needs_git_2_48
def test_closing_a_subtask_with_unpushed_commits_tells_what_to_do_there(serve, parent, lead):
    """agent close・children_close の誤りは、workspace close の --discard-local ではなく、その場でできる手順を案内する。"""
    child = agents.load(ok(call(serve, parent, "children_start", registration="worker", kind="subtask",
                                brief="目的：直す"))["id"])
    commit(Module.find(child.root, github=lead.repository.github), "a.txt")             # push していない
    idle(serve, child)
    refused = call(serve, parent, "children_close", id=child.id)
    assert not refused["ok"] and refused["error"]["code"] == ErrorCode.UNFINISHED_WORK
    hint = refused["error"]["hint"]
    assert f'ecobuild workspace close "{child.root}" --discard-local' in hint and "agent close" in hint
    assert child.root.exists() and agents.load(child.id)


def test_tools_go_through_the_requests_to_the_serve(lead, parent, tmp_path):
    """MCP のツール（children_*）は頼みとして自分の置き場所の requests/ に書き、このPCの係が実行する。"""
    fake = Fake(tmp_path)
    serve = agent_serve.Serve(lambda args, cwd, **_: {"ok": True, "result": {}}, launch=fake)
    stop = threading.Event()
    threading.Thread(target=agent_serve.serve_forever, args=(serve, stop, 0.05), daemon=True).start()
    try:
        context = mcp.Context(parent.id, registry.load("manager"), mcp.OWNER, lead.root)
        tools = {tool.name: tool for tool in children.tools(context)}
        assert set(tools) == set(children.TOOLS)
        assert tools["children_start"].input_schema["required"] == ["registration", "kind", "brief"]
        doc = tools["children_start"].call({"registration": "worker", "kind": "helper", "brief": "調べて"})
        assert doc["ok"] and agents.load(doc["result"]["id"]).parent == parent.id
        listed = tools["children_list"].call({})
        assert [m["id"] for m in listed["result"]["members"]] == [doc["result"]["id"]]
        assert not tools["children_send"].call({"id": parent.id, "text": "x"})["ok"]
    finally:
        stop.set()
        for agent in serve.apps.agents():
            serve.apps.stop(agent.agent_id, 5)


def test_the_tools_are_only_those_the_registration_allows(lead, parent):
    write_registration("reader", tools=["children_list", "task_status"], children_=[])
    context = mcp.Context(parent.id, registry.load("reader"), mcp.OWNER, lead.root)
    catalog = {"commands": [{"path": "task status", "runnable": True, "agent": "read"},
                            {"path": "task submit", "runnable": True, "agent": "owner"}]}
    names = [tool.name for tool in mcp.tools(context, catalog, lambda argv: {}, registry.allows_tool)]
    assert names == ["task_status", "children_list"]


def test_the_notice_reads_the_state_line_and_the_area():
    assert children.reported_state("状態：続ける\n…\n> 状態: 完了") == children.DONE    # 最後の行
    assert children.reported_state("状態はよいです") == children.UNKNOWN_STATE
    assert children.brief_area("# 任せる\n## 持ち場\n- `src/a/`（画面）\n* src/b.py：説明\n1. tests/*.py\n"
                               "## 返してほしいもの\n- 報告\n### 触らない\n- src/c\n") \
        == (("src/a/", "src/b.py", "tests/*.py"), ("src/c",))
    facts = children.ReplyFacts(state=children.DONE, reported=True, pull=3, pull_state="open", checked=False,
                                unknown=("提出（HTTP 502）",))
    found = children.cautions(facts)
    assert "--no-check で提出しました（check を通していません）" in found and "調べられませんでした：提出（HTTP 502）" in found
    assert children.cautions(children.ReplyFacts(state=children.DONE, reported=True, no_submit=True)) == []


def test_the_folder_of_requests_inside_the_container(monkeypatch, tmp_path):
    import ecobuild_container as container
    monkeypatch.setenv(container.INSIDE, "1")
    assert children.requests_folder("a-0123456789") == Path(agent_status.INSIDE) / "a-0123456789" / children.REQUESTS


def test_a_missing_serve_is_told(monkeypatch, tmp_path, parent):
    folder = tmp_path / "requests"
    folder.mkdir()
    agent_status._write(folder / children.SERVE_BEAT, {"at": time.time() - 60})
    with pytest.raises(EcoBuildError) as stopped:
        children.forward(folder, {"tool": "children_list", "arguments": {}, "agent": parent.id})
    assert "止まっています" in stopped.value.message
