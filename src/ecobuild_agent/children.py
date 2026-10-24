"""子のエージェント：エージェントが直接起動した子を扱う（エージェント専用のツール children_*・report_to_parent）。

子は2種類（どちらも親の記録 agents の parent で親子をたどる。作業空間は入れ子にしない）：
- 手伝い（helper）：親と同じ作業空間で、タスクを持たずに親のタスクを手伝う（コミット・提出しない：関所とツールが止める）。
- 子タスク（subtask）：親のタスクの子タスク（Issue）と、そのタスクブランチを取り出した作業空間（Module.start_task。
  元の clone の .ecobuild/w/<番号>）で、タスクの持ち主として働く。提出は親のタスクブランチへの PR。

決まりは文書で頼まずに、ここで止める：扱えるのは直接の子だけ・起動してよい登録（登録の children）だけ・自分より強い登録は
起動しない・子の数は登録の max_children まで・手伝いは子タスクを作らず取り込まない。呼び手は、MCP の引数ではなく、
起動のときに固定した ID（頼みを書いた置き場所）で決まる。

ツールはコンテナの中の MCP サーバー（ecobuild agent mcp）から呼ばれ、このPCには届かないので、頼み（REQUESTS）として
自分の状態の置き場所に書き、このPCの係（serve）が確かめて実行し、結果を書き戻す（forward が待つ）。頼みは
{"tool", "arguments", "agent"}。人の操作（agent restart・takeover・close 等）も、係が持つものを扱うので同じ道で頼む
（{"args", "cwd"}）。

返答の終わり：子の返答が終わると、係が作業空間・GitHub を調べた事実（reply_facts）と注意を添えて、親の受け箱に知らせる
（parent_notice）。手伝いは提出しないので、事実は調べずに状態と最後の返答だけを知らせる。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import ecobuild_container as container
from ecobuild.errors import EcoBuildError
from ecoagent.mcp import Tool, ToolError

from . import agents, mcp, registry
from . import status as agent_status
from .errors import ErrorCode

HELPER, SUBTASK = "helper", "subtask"   # children_start の kind：手伝い・子タスク
START_KINDS = (HELPER, SUBTASK)
BRIEF_FILE = ".ecobuild/ai/brief.md"        # 子タスクの作業空間の中：任された仕事
REPORT_FILE = ".ecobuild/ai/report.md"      # 子タスクの作業空間の中：報告
PROGRESS_FILE = ".ecobuild/ai/progress.md"  # 子タスクの作業空間の中：途中経過（起動し直したときに読む）
BRIEF_COPY = "brief.md"                     # 子の状態の置き場所の中：任された仕事の控え（手伝いはこちらだけ）
REPORT_COPY = "report.md"                   # 子の状態の置き場所の中：report_to_parent で知らせた報告の控え
ARCHIVE = ".ecobuild/ai/children-archive"   # 親の作業空間の中：閉じた子の報告・任された仕事（<ID>-<名前>/）
KEPT = (REPORT_FILE, BRIEF_FILE, PROGRESS_FILE)   # 閉じる前に ARCHIVE へ写す、子タスクの作業空間のもの
REQUESTS = "requests"               # 状態の置き場所の中の、頼みの置き場所
REQUEST_TIMEOUT = 1800              # 頼みの結果を待つ秒数（子タスクの作成・CI を待つ取り込みで長くかかる）
STALL_SECONDS = 120                 # 頼みを実行する ecobuild が、この秒数なにも経過を出さなければ止まったとみなす（係が止める）
PROGRESS = ".progress"              # 頼みの置き場所の中：<id>.progress（係が書く途中経過。.json にしない：頼みと取り違える）
SERVE_SILENT = 30                   # 途中経過がこの秒数書かれなければ、係が止まったとみなす
SERVE_BEAT = "serve.alive"          # 頼みの置き場所の中：係が動いている印（BEAT_EVERY 秒ごと。.json にしない）
BEAT_EVERY = 5
BEAT_STALE = 20                     # 印がこの秒数より古ければ、頼まずに（待たずに）止める
SENT = "sent.jsonl"   # 子の状態の置き場所の中：送った言付け（番号・時刻・頭。取り消したもの）。届いたかは受け箱で見る
SENT_SHOWN = 20       # 一覧の messages に出す、新しいほうからの数
REPORTED = "reported.json"   # 子の状態の置き場所の中：report_to_parent で知らせた時刻
FACTS = "facts.json"         # 子の状態の置き場所の中：最後の返答の終わりに係がそろえた事実（一覧が GitHub に聞かずに読む）
REPORT_KIND = "report"       # 受け箱のものの種類：子が report_to_parent で出した知らせ

FIRST_PROMPT = (f"{BRIEF_FILE} に任された仕事があります。読んで作業を始めてください。終わったら {REPORT_FILE} に報告を書き、"
                "提出してください。返答の最後は「状態：…」の行です。")
RESTART_PROMPT = ("親があなたを起動し直しました（前の会話は引き継いでいません）。次の順で確かめてから続けてください："
                  f"①{BRIEF_FILE}・{PROGRESS_FILE}（前の会話の途中経過） ②task_status・log のツール "
                  f"③{REPORT_FILE}・作業空間の状態（未コミットの変更） "
                  "④前の会話で待っていたもの（テスト・ビルド等）があれば、その結果を自分で確かめる ⑤残りを進める。"
                  "最初の返答に、どこまで進んでいたかを1〜2行で書き、返答の最後は「状態：…」の行にしてください。")
RESUME_PROMPT = ("親があなたを起動し直しました（この会話の続きです）。止まっていたところから続けてください。"
                 "待っていた結果があれば先に確かめ、返答の最後は「状態：…」の行にしてください。")

TOOLS = ("children_list", "children_start", "children_send", "children_cancel", "children_stop", "children_restart",
         "children_log", "children_accept", "children_close", "report_to_parent")


def _id(text: str = "子の ID（a- で始まる。children_list で見られる）") -> dict:
    return {"type": "string", "description": text}


SCHEMAS = {   # ツールの入力の形（呼び手の ID は入れない：起動のときに固定した ID で決まる）
    "children_list": ({}, ()),
    "children_start": ({"registration": {"type": "string", "description": "起動する登録の名前（自分の登録の children にあるもの）"},
                        "kind": {"type": "string", "enum": list(START_KINDS),
                                 "description": "helper：この作業空間の手伝い（タスクなし・コミットしない）。subtask：子タスクと、"
                                                "その作業空間・タスクブランチを作る（提出はこのタスクブランチへの PR）"},
                        "brief": {"type": "string", "description": "任せる仕事：目的・返してほしいもの・使ってよい道具・範囲"},
                        "title": {"type": "string", "description": "子の名前（子タスクなら Issue の題名・ブランチの名前にもなる。"
                                                                   "省けば登録の名前と番号・任せる仕事の頭）"}},
                       ("registration", "kind", "brief")),
    "children_send": ({"id": _id(), "text": {"type": "string", "description": "伝えること（作業中でも次の区切りで届く）"}},
                      ("id", "text")),
    "children_cancel": ({"id": _id(), "message": {"type": "string", "description": "まだ届いていない言付けの番号（children_send の結果）"}},
                        ("id", "message")),
    "children_stop": ({"id": _id()}, ("id",)),
    "children_restart": ({"id": _id(), "resume": {"type": "boolean", "default": False,
                                                  "description": "前の会話の続きから（既定は新しい会話で、どこまで進んだかを確かめてから続ける）"}},
                         ("id",)),
    "children_log": ({"id": _id(), "tail": {"type": "integer", "default": 50, "description": "新しいほうからの出来事の数（0 ですべて）"}},
                     ("id",)),
    "children_accept": ({"id": _id()}, ("id",)),
    "children_close": ({"id": _id()}, ("id",)),
    "report_to_parent": ({"text": {"type": "string", "description": "親に知らせること（質問・区切りの要約・完了の報告。結論を先頭に）"}},
                         ("text",)),
}
DESCRIPTIONS = {
    "children_list": "直接の子の全員の様子（作業中・待機中・止まっている・起動中、その長さ、今していること、最後の返答、提出・報告、"
                     "届いた言付け）を毎回まとめて出します。起動中（コンテナの用意で数分かかる）の子は、起動し直さずに待ちます。",
    "children_start": "子のエージェントを起動します（手伝い helper か、子タスク subtask）。起動は ECOBuild の係が画面なしで行い、"
                      "子の返答が終わると知らせが届きます。",
    "children_send": "子に言付けを送ります（作業中でも、返答を止めずに次の区切りで届きます。止まっている子は、続きから起こして"
                     "届けます。起こせなければ結果の note にわけがあります）。結果の message_id で取り消せます。",
    "children_cancel": "子へのまだ届いていない言付けを取り消します。",
    "children_stop": "子を止めます（返答を終えさせてから）。",
    "children_restart": "子を起動し直します（作業空間・作業はそのまま）。",
    "children_log": "子がしてきたこと（入力・使った道具・返答・返答の終わり）を読みます。",
    "children_accept": "子タスクの提出を、このタスクブランチに取り込みます（取り込み・手元を最新に・子を閉じる、を一度に）。"
                       "閉じられないときは何もしません。",
    "children_close": "子を閉じます（子タスクなら作業空間ごと消します。報告・任された仕事は控えに写します）。",
    "report_to_parent": "親に知らせます（質問・区切りの要約・完了）。親の受け箱に届きます。",
}


# ---- 呼び手と子 -------------------------------------------------------------------------------------------

def child_of(caller: agents.AgentRecord, child_id: str) -> agents.AgentRecord:
    """呼び手の直接の子 child_id の記録（直接の子でなければ止める：孫・ほかの人の子は扱わない）。"""
    try:
        child = agents.load(str(child_id or ""))
    except EcoBuildError:
        child = None
    if child is None or child.parent != caller.id:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{child_id} は、あなたの直接の子ではありません。",
                            hint="扱えるのは自分が起動した子だけです（children_list で見られます）。")
    return child


def _registration(record: agents.AgentRecord) -> registry.Registration:
    """記録の登録（その作業空間のモジュールの、作成元に取り込まれたもの）。"""
    try:
        return registry.effective(record.registration, record.workspace)
    except EcoBuildError:   # 消された登録：子は起動できない・ツールもない
        return registry.Registration(name=record.registration, title=record.registration, document="")


def check_start(caller: agents.AgentRecord, registration: str, kind: str, brief: str) -> registry.Registration:
    """子を起動してよいか（起動してよい登録・自分より強くない・子の数の上限・種類）。子の登録を返す。"""
    mine = _registration(caller)
    if kind not in START_KINDS:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"kind は {'・'.join(START_KINDS)} のどれかです：{kind}")
    if not brief.strip():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "任せる仕事（brief）が空です。",
                            hint="目的・返してほしいもの・使ってよい道具・範囲（やらないこと）を書いてください。")
    if registration not in mine.children:
        allowed = "・".join(mine.children) or "なし"
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                            f"登録「{registration}」は、あなた（登録「{mine.name}」）が起動してよい子ではありません。",
                            hint=f"起動してよい子：{allowed}")
    found = registry.effective(registration, caller.workspace)   # 子は同じモジュールの登録
    if registry.stronger(found, mine):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                            f"登録「{registration}」は、あなた（登録「{mine.name}」）より強い（許すツールが多い）ので起動できません。")
    count = len(agents.children(caller.id))
    if count >= mine.max_children:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"子の数が上限（{mine.max_children}）に達しています（今 {count}）。",
                            hint="終わった子を children_close（子タスクなら children_accept）で閉じてから起動してください。")
    if kind == SUBTASK and caller.kind == agents.HELPER:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "手伝いは子タスクを作れません（タスクの持ち主がすることです）。",
                            hint="この作業空間の中の手伝い（kind helper）なら起動できます。")
    return found


def start(module, caller: agents.AgentRecord, *, registration: str, kind: str, brief: str, title: str = "",
          progress=lambda message: None) -> tuple[agents.AgentRecord, str]:
    """呼び手 caller の子を作る（起動はしない：係がアプリ用で起動する）。module：呼び手の作業空間の Module。
    (子の記録, 最初の発言) を返す。手伝いは同じ作業空間に記録だけ、子タスクは Issue と作業空間を作る。"""
    title = " ".join(title.split())
    if kind == HELPER:
        # 係は手伝いの起動を並べて行うので、子の数の確かめと記録を作るのを、呼び手ごとに1つずつ（上限・連番の名前を守る）
        with _start_lock(caller.id):
            found = check_start(caller, registration, kind, brief)
            record = agents.create(registration=found.name, workspace=caller.root, kind=agents.HELPER, parent=caller.id,
                                   task=caller.task, name=title, model=found.model)
        _write(record.folder / BRIEF_COPY, brief)
        return record, helper_prompt(record, brief)
    with _start_lock(caller.id):
        found = check_start(caller, registration, kind, brief)
    from ecowork import model as _work
    task_branch = module.require_task_branch("子タスクの作成")
    subject = title or _subject(brief) or found.name
    progress(f"子タスク「{subject}」を作っています…")
    issue = module.repository.create_task(subject, body=brief, parent=task_branch.number)
    try:
        progress(f"子タスク #{issue.number} の作業空間を用意しています…")
        child = module.start_task(issue.number, name=_work.branch_label(subject)[:40] or found.name)
        _inherit_container(module.root, child.root)
        child.prepare_agent_area()
        _write(child.root / BRIEF_FILE, brief)
    except Exception as error:
        left = _close_task(module, issue.number, subject, error)
        raise EcoBuildError(getattr(error, "code", None) or ErrorCode.AGENT_ERROR,
                            f"子タスク「{subject}」を作れませんでした：{_message(error)}",
                            hint=getattr(error, "hint", None),
                            details=[f"子タスク：#{issue.number}（{'開いたまま：' + left if left else '閉じた'}）"]) from error
    branch = child.repository.git.current_branch() or ""
    record = agents.create(registration=found.name, workspace=child.root, kind=agents.OWNER, parent=caller.id,
                           task={"number": issue.number, "branch": branch}, name=title, model=found.model)
    _write(record.folder / BRIEF_COPY, brief)
    return record, found.first_prompt or FIRST_PROMPT


_start_locks: dict[str, threading.Lock] = {}
_start_locks_guard = threading.Lock()


def _start_lock(agent_id: str) -> threading.Lock:
    """呼び手 agent_id の子を作るときのロック（係は1つのプロセスなので、スレッドのロックで足りる）。"""
    with _start_locks_guard:
        return _start_locks.setdefault(agent_id, threading.Lock())


def helper_prompt(record: agents.AgentRecord, brief: str, *, restarted: bool = False) -> str:
    """手伝いの最初の発言：任された仕事そのもの（作業空間の brief.md は持ち主のものなので使わない）。"""
    head = ("親があなたを起動し直しました（前の会話は引き継いでいません）。作業空間の様子を確かめてから続けてください。"
            if restarted else "親から任された仕事です。")
    return (f"{head}あなたは手伝いです（この作業空間で、コミット・提出はしません）。終わったら結果を report_to_parent で"
            f"親に知らせ、返答の最後は「状態：…」の行にしてください。\n\n{brief.strip()}")


def _subject(brief: str) -> str:
    """任せる仕事の頭（Issue の題名）。"""
    for line in brief.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:60]
    return ""


def _close_task(module, number: int, subject: str, error: Exception) -> str:
    """作りかけの子タスクを「対応しない」として閉じる（理由をコメントに）。閉じられなければ、そのわけ。"""
    tracker = module.repository.tracker
    try:
        tracker.comment(number, f"ECOBuild：「{subject}」の作成が途中で失敗したため閉じます（{_message(error)}）。")
    except Exception:
        pass   # 閉じるのを優先する
    try:
        tracker.close(number, not_planned=True)
    except Exception as problem:
        return _message(problem)
    return ""


def stop_container(root: Path, progress=lambda message: None) -> bool:
    """子タスクの作業空間 root のコンテナを止める（取り込む・閉じる前に。中のエージェントを止めても、コンテナは
    sleep infinity で動き続け、WSL・メモリーを使い続ける）。Docker が使えなければ何もしない。止めたか。"""
    try:
        if not container.enabled(root):
            return False
        progress("作業空間のコンテナを止めています…")
        return container.stop(root).changed
    except EcoBuildError:
        return False


def _inherit_container(parent: Path, child: Path) -> None:
    """親の作業空間のコンテナの選択（コンテナにするか・イメージ・使わせないもの）を、子タスクの作業空間にも。"""
    from ecobuild import config as _config
    from .inside import DENY_KEY
    chosen = {key: value for key, value in _config.load_local(parent).items()
              if key in (container.KEY, container.IMAGE_KEY, DENY_KEY)}
    if chosen:
        _config.save_local(child, {**_config.load_local(child), **chosen})


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def _message(error: Exception) -> str:
    return getattr(error, "message", None) or str(error) or type(error).__name__


def restart_prompt(child: agents.AgentRecord, *, resume: bool) -> tuple[str, str]:
    """起動し直すときの (最初の発言, 続きからの会話)。resume：前の会話の続きから（会話が分からなければ止める）。"""
    if resume:
        session = agent_status.session_of(child.folder) or child.session
        if not session:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"「{child.name}」の前の会話が分かりません。",
                                hint="resume なしで、新しい会話で起動し直してください（作業空間の作業はそのままです）。")
        return RESUME_PROMPT, session
    if child.kind == agents.HELPER:
        return helper_prompt(child, _read_text(child.folder / BRIEF_COPY), restarted=True), ""
    return RESTART_PROMPT, ""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""


# ---- 様子 -------------------------------------------------------------------------------------------------

def describe_activity(member: dict, now: float | None = None) -> str:
    """様子の1行：作業中（12分）・待機中・止まっている・起動中、と届いていない言付け・コンテキスト。"""
    now = time.time() if now is None else now
    state = member.get("state") or ""
    text = agent_status.STATE_NAMES.get(state, "")
    if not text:
        return ""
    since = member.get("since")
    if isinstance(since, (int, float)) and state in (agent_status.WORKING, agent_status.IDLE, agent_status.STARTING):
        text += f"（{_duration(now - since)}）"
    if member.get("doing") and state == agent_status.WORKING:
        text += f"  今：{member['doing']}"
    if member.get("waiting"):
        text += f"  届いていない言付け {member['waiting']}"
    if isinstance(member.get("context"), (int, float)):
        text += f"  コンテキスト {round(member['context'])}%"
    return text


def _duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}秒"
    if seconds < 3600:
        return f"{seconds // 60}分"
    return f"{seconds // 3600}時間{seconds % 3600 // 60}分"


def shown(record: agents.AgentRecord) -> dict:
    """1人の記録と様子（JSON の形）：記録の項目（id・name・registration・kind・parent・task・workspace 等）と、
    path・branch・session、activity の項目（state・since・last_reply 等）。"""
    folder = record.folder
    task = record.task or {}
    return {**agents.to_data(record), "path": Path(record.workspace).as_posix(), "branch": task.get("branch") or "",
            "session": agent_status.session_of(folder) or record.session, **agent_status.activity(folder)}


def details(record: agents.AgentRecord) -> dict:
    """一覧に足す、子の手元の記録（GitHub に聞かない・係を通さない）：submission（最後の返答の終わりに係が見た提出）・
    dirty（未コミットのファイル）・ahead（push していないコミット）・facts_at・messages（送った言付けと届いたか）・
    replies（返答を終えた回数）・reported（報告がある）・report_at（報告を更新した時刻）・report_told（report_to_parent で
    知らせた時刻）・report_read（その知らせが親に届いたか。知らせていなければ None）。"""
    folder = record.folder
    facts = saved_facts(folder)
    pull = facts.get("pull")
    report = folder / REPORT_COPY if record.kind == agents.HELPER else Path(record.workspace) / REPORT_FILE
    try:
        report_at = report.stat().st_mtime
    except OSError:
        report_at = None
    told = agent_status.read(folder / REPORTED)
    told = told if isinstance(told, dict) else None
    parent = _load_or_none(record.parent)
    return {"submission": {"pull": pull, "state": facts.get("pull_state"), "checked": facts.get("checked"),
                           "head": facts.get("pull_head") or "", "at": facts.get("pulled_at")} if pull else None,
            "dirty": list(facts.get("uncommitted") or ()), "ahead": facts.get("unpushed") or 0, "facts_at": facts.get("at"),
            "messages": messages(folder), "replies": agent_status.replies(folder), "reported": report_at is not None,
            "report_at": report_at, "report_told": told.get("at") if told else None,
            "report_read": None if told is None else parent is not None and str(told.get("id") or "")
            not in agent_status.waiting_ids(parent.folder)}


def listed(record: agents.AgentRecord, *, recent: int = 0, describe=None, nested: bool = False,
           depth: int = 0) -> list[dict]:
    """record の直接の子の全員（起動した順）。recent：1人ごとに、最新の出来事の人向けの行（describe(出来事) → 行か None。
    使う側が渡す）をこの数だけ recent に。nested：子の子も members に（8段まで）。"""
    from . import app
    found = []
    for child in agents.children(record.id):
        item = {**shown(child), **details(child)}
        if recent > 0 and describe is not None:
            item["recent"] = [text for text in map(describe, app.recent_events(child.folder)) if text][-recent:]
        if nested and depth < 8:
            item["members"] = listed(child, recent=recent, describe=describe, nested=True, depth=depth + 1)
        found.append(item)
    return found


def _load_or_none(agent_id: str | None) -> agents.AgentRecord | None:
    if not agent_id:
        return None
    try:
        return agents.load(agent_id)
    except EcoBuildError:
        return None


# ---- 言付け -----------------------------------------------------------------------------------------------

def send(child: agents.AgentRecord, text: str, *, sender: str) -> str:
    """子（child）の受け箱に言付けを入れる。sender：送り手の表示（[… から] として頭に付ける）。言付けの番号を返す。"""
    if not text.strip():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "伝えることが空です。")
    file = agent_status.put(child.folder, f"[{sender}から] {text}", sender=sender)
    key = agent_status.item_id(file)
    _log_sent(child.folder, {"id": key, "at": time.time(), "text": " ".join(text.split())[:80]})
    return key


def cancel(child: agents.AgentRecord, key: str) -> str:
    """まだ届いていない言付け key を取り消す（受け箱から出す）。届いた後なら止める。"""
    folder = child.folder
    if not any(entry["id"] == key for entry in messages(folder, limit=10 ** 6)):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"「{child.name}」へ送った言付けに {key} はありません。",
                            hint="番号は送ったときの結果・children_list の messages で分かります。")
    if not agent_status.withdraw(folder, key):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"言付け {key} は、もう届いています（取り消せません）。",
                            hint="直したいことは、もう一度送ってください。")
    _log_sent(folder, {"id": key, "cancelled": time.time()})
    return key


def sender_of(record: agents.AgentRecord) -> str:
    """言付け・知らせの頭に書く、送り手の表示。"""
    return f"親「{record.name}」（{record.id}）"


def _log_sent(folder: Path, entry: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / SENT, "a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def messages(folder: Path, limit: int = SENT_SHOWN) -> list[dict]:
    """送った言付け：[{id, sent（時刻）, delivered（届いた）, cancelled, text}]。古い順。"""
    found: dict[str, dict] = {}
    try:
        lines = (Path(folder) / SENT).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        if entry.get("cancelled"):
            if entry["id"] in found:
                found[entry["id"]]["cancelled"] = True
            continue
        found[entry["id"]] = {"id": entry["id"], "sent": entry.get("at"), "text": entry.get("text", ""), "cancelled": False}
    waiting = agent_status.waiting_ids(folder)
    shown_ = list(found.values())[-limit:]
    for entry in shown_:
        entry["delivered"] = not entry["cancelled"] and entry["id"] not in waiting
    return shown_


def report(record: agents.AgentRecord, text: str) -> dict:
    """子（record）が親に知らせる（report_to_parent）：親の受け箱に入れ、控えを状態の置き場所の REPORT_COPY に残す。"""
    if not text.strip():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "知らせることが空です。")
    parent = _load_or_none(record.parent)
    if parent is None:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "あなたには親がいません（人が起動したエージェントです）。",
                            hint="人へは、返答で伝えてください。")
    _write(record.folder / REPORT_COPY, text)
    put = agent_status.put(parent.folder, f"[ECOBuild] {_who(record)}から知らせです：\n{text.strip()}",
                           sender=record.id, kind=REPORT_KIND)
    told = {"at": time.time(), "id": agent_status.item_id(put)}
    agent_status._write(record.folder / REPORTED, told)
    return {"id": record.id, "parent": parent.id, **told}


def _who(record: agents.AgentRecord) -> str:
    kind = "手伝い" if record.kind == agents.HELPER else f"子タスク #{(record.task or {}).get('number')}"
    return f"子「{record.name}」（{record.id}・{kind}）"


# ---- 閉じる -----------------------------------------------------------------------------------------------

def close_problems(child: agents.AgentRecord) -> list[str]:
    """子を閉じる・取り込む前に止めるわけ：作業中・届いていない言付け（動いている・起動中の子だけ。止まっている子には
    届かないので、閉じるのを止めない）・提出の後のコミット・閉じていない子。"""
    from ecowork.git import Git
    found = []
    seen = agent_status.activity(child.folder)
    if seen["state"] == agent_status.WORKING:
        found.append(f"「{child.name}」は作業中です")
    if seen.get("waiting") and seen["state"] in (agent_status.WORKING, agent_status.IDLE, agent_status.STARTING):
        found.append(f"「{child.name}」にまだ届いていない言付けが {seen['waiting']} 件あります")
    grandchildren = agents.children(child.id)
    if grandchildren:
        found.append(f"「{child.name}」にはまだ子がいます（" + "、".join(g.name for g in grandchildren) + "。先に閉じてください）")
    facts = saved_facts(child.folder)
    if child.kind == agents.OWNER and facts.get("pull") and facts.get("pull_head") \
            and facts.get("pull_state") in ("open", "merged"):
        try:
            head = Git(child.root).output("rev-parse", "HEAD").strip()
        except Exception:
            head = ""
        if head and not head.startswith(facts["pull_head"]) and not facts["pull_head"].startswith(head):
            found.append(f"「{child.name}」には、提出（PR #{facts['pull']}）の後のコミットがあります")
    return found


def own_workspace(child: agents.AgentRecord) -> bool:
    """子が自分の作業空間（子タスク）を持つか（親と同じ作業空間の手伝い・人が起動したものは持たない）。"""
    parent = _load_or_none(child.parent)
    return child.kind == agents.OWNER and parent is not None and not _same(child.workspace, parent.workspace)


def unpushed_files(child: agents.AgentRecord) -> list[str]:
    """子タスクの作業空間の、GitHub にないファイル（未コミットの変更・新しいファイル）。"""
    from ecowork.git import Git
    try:
        tree = Git(child.root).working_tree()
    except Exception:
        return []
    return list(dict.fromkeys(tree.staged + tree.unstaged + tree.conflicted + tree.untracked))


def archive(child: agents.AgentRecord) -> list[str]:
    """閉じる前に、子の報告・任された仕事・途中経過を、親の作業空間の ARCHIVE/<ID>-<名前>/ へ写す。写したもの。"""
    import shutil
    parent = _load_or_none(child.parent)
    if parent is None:
        return []
    folder = f"{child.id}-{_safe(child.name)}"
    target = Path(parent.workspace) / ARCHIVE / folder
    sources = [(child.folder / name, name) for name in (BRIEF_COPY, REPORT_COPY)]
    if own_workspace(child):
        sources += [(child.root / name, Path(name).name) for name in KEPT]
    kept = []
    for source, name in sources:
        if source.is_file():
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target / name)
            kept.append(f"{ARCHIVE}/{folder}/{name}")
    return list(dict.fromkeys(kept))


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "-", name).strip("-.") or "child"


def forget(child: agents.AgentRecord) -> None:
    """閉じた子の記録と置き場所を消し、親の受け箱のその子からのまだ届いていない知らせも消す。"""
    parent = _load_or_none(child.parent)
    if parent is not None:
        agent_status.forget_from(parent.folder, child.id)
    agents.forget(child.id)


def _same(a, b) -> bool:
    try:
        return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))
    except OSError:
        return False


# ---- 返答の終わり：係が事実をそろえて、親に知らせる ---------------------------------------------------------
# 子の自己申告（状態の行・報告）だけに頼らず、係が作業空間と GitHub を直接調べ、食い違い・注意を先頭に書く
# （親は注意のないものを差分だけ見て取り込み、注意のあるものは中を見る：レビューの負荷を下げる）。

DONE, QUESTION, STUCK, GOING = "完了", "質問あり", "止まっている", "続ける"
STATES = (DONE, QUESTION, STUCK, GOING)   # 子が返答の最後の1行「状態：…」に書くもの
UNKNOWN_STATE = "不明"                    # 状態の行がない
_STATE_LINE = re.compile(rf"^[\s>*_`-]*状態[\s*_`]*[：:][\s*_`]*({'|'.join(STATES)})", re.MULTILINE)
NO_SUBMIT = "提出しない"                   # 任せる内容（brief）にこれがあれば、報告だけの仕事（レビュー・調べもの等）
AREA_HEADING, KEEP_OUT_HEADING = "持ち場", "触らない"   # 任せる内容（brief）の節：変えてよいパス・触らないパス
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*#*\s*$")
_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$")
_LISTED = 3                               # 注意に並べるファイルの数（ほかは「ほか n 件」）


@dataclass(frozen=True)
class ReplyFacts:
    """子タスクの子の返答が終わったときに、係がその作業空間・GitHub を調べてそろえた事実（parent_notice の文のもと）。"""
    state: str                          # 子の言う状態（STATES。行がなければ UNKNOWN_STATE）
    reported: bool                      # 報告（REPORT_FILE）がある
    no_submit: bool = False             # 任された仕事が報告だけ（NO_SUBMIT）：提出がなくてよい
    pull: int | None = None             # 提出（タスクブランチの PR。いちばん新しいもの）の番号
    pull_state: str = ""                # open・merged・closed
    draft: bool = False
    pull_head: str = ""                 # 提出の版（PR の先頭のコミット）
    pulled_at: float | None = None      # その時刻（手元の git で分かれば）
    checked: bool | None = None         # 提出のときに check を通したか（--no-check なら False。分からなければ None）
    unchecked_since: bool = False       # check を通した版の後に、提出に入ったコミットがある（出し直していない）
    uncommitted: tuple[str, ...] = ()   # 未コミットの変更（新しいファイルも）
    unpushed: int = 0                   # push していないコミットの数
    changed: tuple[str, ...] = ()       # 親のタスクブランチから変えたファイル（未コミットのものも）
    scoped: bool = False                # 任された仕事に持ち場が書いてあり、照らした
    outside: tuple[str, ...] = ()       # 持ち場の外の変更
    kept_out: tuple[str, ...] = ()      # 触らないはずのものの変更
    unknown: tuple[str, ...] = ()       # 調べられなかったこと（何を・なぜ）


def reported_state(message: str) -> str:
    """返答の文の最後の「状態：…」の行（なければ UNKNOWN_STATE）。"""
    found = _STATE_LINE.findall(message or "")
    return found[-1] if found else UNKNOWN_STATE


def brief_area(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """任された仕事（brief）の「持ち場」「触らない」の節の箇条書きのパス：(持ち場, 触らない)。節がなければ空。
    項目の頭のパス（`…` で囲んでいればその中）だけを読み、後ろの説明は読まない。"""
    found = {AREA_HEADING: [], KEEP_OUT_HEADING: []}
    current = None
    for line in (text or "").splitlines():
        heading = _HEADING.match(line)
        if heading:
            current = heading.group(1) if heading.group(1) in found else None
            continue
        item = _ITEM.match(line) if current else None
        if item:
            quoted = re.search(r"`([^`]+)`", item.group(1))
            path = (quoted.group(1) if quoted else re.split(r"[\s（(：:、,]", item.group(1).strip())[0]).strip()
            path = path.removeprefix("./").replace("\\", "/")
            if path:
                found[current].append(path)
    return tuple(found[AREA_HEADING]), tuple(found[KEEP_OUT_HEADING])


def _covers(pattern: str, path: str) -> bool:
    """持ち場等のパス（フォルダー・ファイル・glob）に path が入るか。"""
    import fnmatch
    pattern = pattern.rstrip("/")
    if any(mark in pattern for mark in "*?["):
        return fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(path, pattern + "/*")
    return path == pattern or path.startswith(pattern + "/")


def reply_facts(root: Path, message: str, *, github=None) -> ReplyFacts:
    """子タスクの作業空間 root のエージェントの返答が終わったときの事実を調べる（時間のかかる check は動かさない）。
    調べられなかったものは unknown に書き、ほかは調べ続ける（知らせは必ず出す）。github：試験で差し替える。"""
    from ecobuild.module import submitted_check
    from ecowork import model as _work
    from ecowork.git import REMOTE
    from ecowork.repository import Repository
    root = Path(root)
    unknown = []
    brief = _read_text(root / BRIEF_FILE)
    found = {"state": reported_state(message), "reported": (root / REPORT_FILE).is_file(), "no_submit": NO_SUBMIT in brief}
    repository = Repository(root, github=github)
    git = repository.git
    branch = base = None
    try:
        branch = git.current_branch()
        base = branch and git.get_config(_work.base_key(branch))
        tree = git.working_tree()
        found["uncommitted"] = tuple(dict.fromkeys(tree.staged + tree.unstaged + tree.conflicted + tree.untracked))
        found["unpushed"] = len(git.output("log", "HEAD", "--not", "--remotes", "--format=%h").splitlines())
    except Exception as error:
        unknown.append(f"git の状態（{error}）")
    if base:
        try:
            committed = git.output("diff", "--name-only", f"{REMOTE}/{base}...HEAD").splitlines()
            changed = tuple(dict.fromkeys([*committed, *found.get("uncommitted", ())]))
            found["changed"] = changed
            area, kept_out = brief_area(brief)
            if area:
                found["scoped"] = True
                found["outside"] = tuple(p for p in changed if not any(_covers(a, p) for a in area))
            found["kept_out"] = tuple(p for p in changed if any(_covers(k, p) for k in kept_out))
        except Exception as error:
            unknown.append(f"親のタスクブランチ {base} からの差分（{error}）")
    if branch:
        try:
            pulls = repository.github.pull_requests_for_branch(root, branch)
            if pulls:
                pull = max(pulls, key=lambda p: p.number)
                checked, version = submitted_check(pull.body)
                found.update(pull=pull.number, pull_state=pull.state, draft=pull.draft, checked=checked,
                             unchecked_since=bool(checked and version and pull.head_sha and pull.state == "open"
                                                  and not pull.head_sha.startswith(version)))
                if pull.head_sha:
                    found["pull_head"] = pull.head_sha
                    try:
                        found["pulled_at"] = float(git.output("show", "-s", "--format=%ct", pull.head_sha).strip())
                    except Exception:   # 手元にない版（fetch していない）：時刻は分からない
                        pass
        except Exception as error:
            unknown.append(f"提出（{getattr(error, 'message', error)}）")
    return ReplyFacts(**found, unknown=tuple(unknown))


def save_facts(folder: Path, facts: ReplyFacts) -> None:
    """そろえた事実を子の状態の置き場所に残す（一覧・閉じる前の確かめが読む）。"""
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
        agent_status._write(Path(folder) / FACTS, {**asdict(facts), "at": time.time()})
    except OSError:
        pass


def saved_facts(folder: Path) -> dict:
    """最後に残した事実（なければ空）。"""
    found = agent_status.read(Path(folder) / FACTS)
    return found if isinstance(found, dict) else {}


def _files(paths: tuple[str, ...]) -> str:
    shown_ = "、".join(paths[:_LISTED])
    return shown_ + (f" ほか {len(paths) - _LISTED} 件" if len(paths) > _LISTED else "")


def cautions(facts: ReplyFacts) -> list[str]:
    """知らせの先頭に書く、食い違い・注意（なければ空：差分を見て取り込んでよい）。"""
    found = []
    submitted = facts.pull is not None and facts.pull_state != "closed"
    if facts.state == UNKNOWN_STATE:
        found.append("返答の最後に状態の行がありません（作業中なら途中の区切り：待つ。待機中で変化がなければ、状態の行を書くよう"
                     "言付ける。テスト待ちで返答を終えて止まった可能性もあります）")
    elif facts.state == QUESTION:
        found.append("質問があります（最後の返答を読んで答えてください）")
    elif facts.state == STUCK:
        found.append("止まっていると言っています")
    if facts.state == DONE and not submitted and not facts.no_submit and not any(u.startswith("提出") for u in facts.unknown):
        found.append("完了と言っていますが、提出がありません")
    if facts.state == DONE and not facts.reported:
        found.append("完了と言っていますが、報告がありません")
    if submitted and facts.checked is False:
        found.append("--no-check で提出しました（check を通していません）")
    if facts.unchecked_since:
        found.append("check を通した版の後のコミットが提出に入っています（出し直していません）")
    if facts.uncommitted:
        found.append(f"未コミットの変更があります（{_files(facts.uncommitted)}）")
    if facts.unpushed:
        found.append(f"push していないコミットが {facts.unpushed} 件あります")
    if facts.outside:
        found.append(f"持ち場の外のファイルを変えました（{_files(facts.outside)}）")
    if facts.kept_out:
        found.append(f"触らないはずのファイルを変えました（{_files(facts.kept_out)}）")
    found += [f"調べられませんでした：{item}" for item in facts.unknown]
    return found


def _facts_line(facts: ReplyFacts, report_line: str) -> str:
    """状態と事実の1行。"""
    if facts.pull is None:
        submission = "なし"
    else:
        kind = {"open": "下書き" if facts.draft else "開いている", "merged": "取り込み済み", "closed": "閉じた"}
        checked = {True: "・check を通した", False: "・--no-check", None: ""}[facts.checked]
        submission = f"PR #{facts.pull}（{kind.get(facts.pull_state, facts.pull_state)}{checked}）"
    changed = f"変えたファイル {len(facts.changed)}" + ("" if facts.scoped or not facts.changed else "（持ち場は照らしていません）")
    return f"状態：{facts.state}。{report_line}提出：{submission}。{changed}。"


def _clock(at: float) -> str:
    return time.strftime("%m/%d %H:%M", time.localtime(at))


def _report_line(root: Path, reported: bool, last_sent: float | None) -> str:
    """報告の1行：場所と、更新した時刻・最後の言付けより前か後か（前なら古い報告かもしれない）。"""
    if not reported:
        return f"報告：まだありません（{REPORT_FILE}）。"
    try:
        changed = (Path(root) / REPORT_FILE).stat().st_mtime
    except OSError:
        return f"報告：{REPORT_FILE}。"
    when = f"更新 {_clock(changed)}"
    if last_sent is not None:
        when += "、最後の言付けより後" if changed >= last_sent else "、最後の言付けより前（言付けの後は書き直していません）"
    return f"報告：{REPORT_FILE}（{when}）。"


def _submission_line(facts: ReplyFacts, last_sent: float | None) -> str:
    """提出が最後の言付けより前か後か（前なら、言付けの後に出し直していない）。"""
    if facts.pull is None or facts.pulled_at is None or last_sent is None or facts.pull_state == "closed":
        return ""
    return "提出は最後の言付けより後の版です。" if facts.pulled_at >= last_sent else "提出は最後の言付けより前の版です（出し直していません）。"


def parent_notice(child: agents.AgentRecord, message: str, *, facts: ReplyFacts | None = None, continued: int = 0,
                  merged: int = 0) -> tuple[agents.AgentRecord, str] | None:
    """子（child）の返答が終わったときに、親へ送る知らせ：(親の記録, 文)。親がいなければ None。
    子タスクの子：先頭に注意（なければ「注意なし」）、次に状態と事実、最後に最後の返答の頭。手伝い：状態と最後の返答だけ
    （提出しないので事実は調べない）。facts：そろえた事実（省けば reply_facts で調べ、save_facts で残す）。
    continued：受け箱の言付けを受け取って続けている（返答を終えていない：短く知らせる）。merged：この知らせにまとめた、
    まだ届いていなかった前の知らせの数。"""
    parent = _load_or_none(child.parent)
    if parent is None:
        return None
    folder = child.folder
    count = agent_status.replies(folder)
    who = _who(child) + (f"・返答 {count} 回目" if count else "")
    if continued:
        return parent, f"[ECOBuild] {who}は、言付け {continued} 件を受け取って続けています（返答はまだ終わっていません）。"
    waiting = agent_status.activity(folder).get("waiting") or 0
    extra = (f"届いていない言付け {waiting} 件。" if waiting else "") \
        + (f"（まだ読まれていない前の知らせ {merged} 件を、これにまとめました）" if merged else "")
    last = " ".join((message or "").split())[:400]
    tail = f"\n最後の返答：{last}" if last else ""
    if child.kind == agents.HELPER:
        state = reported_state(message)
        caution = "注意：返答の最後に状態の行がありません" if state == UNKNOWN_STATE else \
            "注意：質問があります（最後の返答を読んで答えてください）" if state == QUESTION else \
            "注意：止まっていると言っています" if state == STUCK else "注意なし"
        return parent, f"[ECOBuild] {who}の返答が終わりました。{caution}\n状態：{state}。（手伝い：提出なし）{extra}{tail}"
    if facts is None:
        facts = reply_facts(child.root, message)
        save_facts(folder, facts)
    sent = [entry["sent"] for entry in messages(folder) if not entry["cancelled"] and isinstance(entry.get("sent"), (int, float))]
    last_sent = max(sent) if sent else None
    found = cautions(facts)
    caution = "注意：" + "／".join(found) if found else "注意なし"
    return parent, (f"[ECOBuild] {who}の返答が終わりました。{caution}\n"
                    f"{_facts_line(facts, _report_line(child.root, facts.reported, last_sent))}"
                    f"{_submission_line(facts, last_sent)}{extra}{tail}")


# ---- 頼み（コンテナの中の MCP サーバー・このPCの端末から、このPCの係へ） ---------------------------------------

def requests_folder(agent_id: str) -> Path:
    """エージェント agent_id の頼みの置き場所（自分の状態の置き場所の中。コンテナの中ではマウントした所）。"""
    if os.environ.get(container.INSIDE):
        return Path(agent_status.inside(agent_id)) / REQUESTS
    return agents.load(agent_id).folder / REQUESTS


def forward(folder: Path, request: dict, *, timeout: float = REQUEST_TIMEOUT, wait=time.sleep,
            progress=lambda message: None) -> dict:
    """このPCの係（agent serve）に頼み（request：{"tool", "arguments", "agent"} か {"args", "cwd"}）を実行してもらい、その
    JSON の結果（{ok, result|error}）を返す。folder：頼みの置き場所。係が動いていなければ（拾われなければ）止める。待つ間、
    係の途中経過を progress に渡し、途中経過が途切れたら（係が止まった）止める。"""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    beat = agent_status.read(folder / SERVE_BEAT)   # 係が動いているか、先に見る（止まっていれば待たない）
    if isinstance(beat, dict) and isinstance(beat.get("at"), (int, float)) and time.time() - beat["at"] > BEAT_STALE:
        raise EcoBuildError(ErrorCode.AGENT_ERROR,
                            f"ECOBuild の係（agent serve）が止まっています（最後に動いていたのは {int(time.time() - beat['at'])} 秒前）。",
                            hint="このPCで GUI を起動し直すか、ecobuild agent serve を起動してから、やり直してください。")
    key = uuid.uuid4().hex
    request_file = folder / f"{key}.json"
    temporary = folder / f"{key}.tmp"
    temporary.write_text(json.dumps({**request, "id": key, "at": time.time()}, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, request_file)
    result = folder / f"{key}.result.json"
    report_file = folder / f"{key}{PROGRESS}"
    started, told, picked = time.monotonic(), None, None
    while time.monotonic() - started < timeout:
        seen = agent_status.read(report_file)
        if picked is None and not request_file.exists():
            picked = time.monotonic()
        if seen is None and picked is not None and not result.is_file() \
                and time.monotonic() - picked > SERVE_SILENT:   # 拾ったのに途中経過を書かない：係が消えた・古い係
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "ECOBuild の係（agent serve）が、頼みを受け取ったまま応えません。",
                                hint="GUI が閉じたか、係が古い ECOBuild のままです。GUI を起動し直してから、様子を確かめて"
                                     "やり直してください。")
        if isinstance(seen, dict) and not result.is_file():
            if seen.get("doing") and seen["doing"] != told:
                told = seen["doing"]
                progress(f"係：{told}")
            if isinstance(seen.get("at"), (int, float)) and time.time() - seen["at"] > SERVE_SILENT:
                raise EcoBuildError(ErrorCode.AGENT_ERROR, "ECOBuild の係（agent serve）が、頼みの途中で止まりました。",
                                    hint="GUI が閉じたか、係が終わったようです。GUI を起動し直してから、様子を確かめて"
                                         "やり直してください。")
        if result.is_file():
            try:
                doc = json.loads(result.read_text(encoding="utf-8"))
            except ValueError:   # 書いている途中
                wait(0.5)
                continue
            result.unlink(missing_ok=True)
            if agents.is_id(folder.parent.name) and not os.environ.get(container.INSIDE) \
                    and not (agent_status.private(folder.parent.name) / agents.RECORD).is_file():
                import shutil   # 頼みでそのエージェントを閉じた（記録が消えた）：結果のために残った置き場所も消す
                shutil.rmtree(folder.parent, ignore_errors=True)
                left = agent_status.directory(folder.parent.name)   # 止めた後に書かれた様子（状態の置き場所）も
                if left is not None:
                    shutil.rmtree(left, ignore_errors=True)
            return doc
        if request_file.exists() and time.monotonic() - started > 15:   # 15秒たっても拾われない：係がいない
            request_file.unlink(missing_ok=True)
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "ECOBuild の係（agent serve）が頼みを受け取りませんでした。",
                                hint="このPCで ecobuild agent serve が動いているか確かめてください（GUI は自分で起動します）。")
        wait(0.5)
    raise EcoBuildError(ErrorCode.AGENT_ERROR, "係の結果を待ちきれませんでした。", hint="GUI の窓・係の様子を確かめてください。")


def human_requests(agent_id: str) -> Path:
    """人の操作の頼みの置き場所（このPCだけ。status.private の中）。コンテナにマウントする状態の置き場所の頼み
    （requests_folder）は、中のエージェントが書けるので、係はそこからはツールの頼みしか受けない。"""
    return agent_status.private(agent_id) / REQUESTS


def ask_serve(record: agents.AgentRecord, args: list[str], progress=lambda message: None) -> dict:
    """人の操作（agent restart・takeover 等）を、エージェント record の人の操作の頼みの置き場所から係に頼み、結果を返す
    （失敗は誤り）。"""
    doc = forward(human_requests(record.id), {"args": [*args, *([] if "--json" in args else ["--json"])], "cwd": "."},
                  progress=progress)
    if not doc.get("ok"):
        error = doc.get("error") or {}
        raise EcoBuildError(error.get("code") or ErrorCode.AGENT_ERROR, error.get("message") or "係での実行に失敗しました。",
                            hint=error.get("hint"), details=error.get("details"))
    return doc.get("result") or {}


def check_arguments(tool: str, arguments) -> dict:
    """ツールの入力を形（SCHEMAS）と照らす（係の側で。知らない入力・足りない入力・型の違いは止める）。"""
    if tool not in SCHEMAS:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"知らないツールです：{tool}")
    if not isinstance(arguments, dict):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "ツールの入力は object です。")
    properties, required = SCHEMAS[tool]
    unknown = sorted(set(arguments) - set(properties))
    if unknown:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"知らない入力です：{', '.join(unknown)}")
    missing = [name for name in required if arguments.get(name) in (None, "")]
    if missing:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{', '.join(missing)} を指定してください。")
    types = {"string": str, "boolean": bool, "integer": int}
    for name, value in arguments.items():
        expected = types[properties[name]["type"]]
        if value is not None and (not isinstance(value, expected) or (expected is int and isinstance(value, bool))):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{name} の値の型が違います（{properties[name]['type']}）。")
        if properties[name].get("enum") and value not in properties[name]["enum"]:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                                f"{name} は {'・'.join(properties[name]['enum'])} のどれかです：{value}")
    return arguments


def tool_schema(tool: str) -> dict:
    properties, required = SCHEMAS[tool]
    schema: dict = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = list(required)
    return schema


@mcp.register_provider
def tools(context: mcp.Context) -> list[Tool]:
    """子を扱うツール（MCP）。どれも頼みとして係に渡す（確かめも実行も係がする。呼び手は context の ID）。"""
    def call(name: str):
        def run(arguments: dict) -> dict:
            try:
                return forward(requests_folder(context.agent_id),
                               {"tool": name, "arguments": arguments, "agent": context.agent_id})
            except EcoBuildError as error:
                raise ToolError(error.message + (f"（{error.hint}）" if error.hint else "")) from error
        return run
    return [Tool(name, DESCRIPTIONS[name], tool_schema(name), call(name)) for name in TOOLS]


__all__ = ["HELPER", "SUBTASK", "START_KINDS", "TOOLS", "ReplyFacts", "archive", "ask_serve", "brief_area", "cautions",
           "check_arguments", "check_start", "child_of", "close_problems", "describe_activity", "details", "forget",
           "forward", "listed", "parent_notice", "report", "reply_facts", "reported_state", "restart_prompt", "send",
           "shown", "start", "tools"]
