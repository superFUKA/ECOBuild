"""進行役・管理役・作業役（エージェントのチーム）。

Anthropic の orchestrator-workers（lead が仕事を分けて任せ、結果をまとめる）に沿わせる：
- 進行役（lead）：ユーザーとのやりとりに特化する。話の流れに応じて、仕事（話題）ごとに管理役を作り（何人でも）、
  話して決めた内容をその仕事の管理役へ send で命令し、管理役からの要約を受け取ってユーザーに伝える。会話の途中で別の
  仕事の話が始まれば、別の管理役を作る。作業役は直接作らない。自分ではファイルを編集しない。
- 管理役（manager）：1つの仕事を受け持つ。計画し、作業役に任せ、返答の終わり・報告の知らせを受け取り、結果を読んで取り込む
  （作業役の知らせは管理役に届き、進行役には届かない）。大きな部分は、下に管理役を作って任せられる。上の役（進行役、
  または作った管理役）へは要約を send で返す。自分ではファイルを編集しない。
- 作業役（worker）：任された1つの仕事を、自分の子タスク＋作業空間で行い、報告を書いて提出する（今の作業空間の
  エージェントと同じ）。

作業役は進行役のタスクの子タスクで、作業空間は進行役の作業空間の中の TEAM_AREA/<番号>-<名前>/（.ecobuild/ai の下：
git の除外の中）。子タスクのタスクブランチは親（進行役）のタスクブランチから作り、提出は親のタスクブランチへの PR に
なる。進行役は自分の場所（コンテナなら /work）から作業役のファイル・報告をそのまま読める。

作業役は ECOBuild の作業役・管理役を作らない（分けたくなったら管理役に提案する）。進行役は管理役を作り、管理役が
作業役と下の管理役を作る（作った人のタスクの子タスクで、作業空間は作った人の作業空間の中）。

コンテナの中の進行役は、このPC（ほかのコンテナ・エージェントを動かしている側）に届かない。作業役を作る等の操作は
「頼み」（REQUESTS）として、状態の置き場所（このPCのフォルダーをマウントしたもの。agent_status）に書き、このPCで常駐する
ECOBuild の係（agent_serve。GUI が起動する）が実行して結果を書き戻す（forward）。GUI の端末の中の進行役（このPC）も、
作業役を係に起動してもらうため同じ道を使う（WINDOW_VARIABLE）。

言付け（send）と、作業役の返答が終わった知らせ（lead_notice）は、相手のエージェントの受け箱（agent_status.put）に入れる。
届けるのはエージェントを動かしている側（係が持つアプリ用のものは係が標準入力へ。人の画面なら GUI の窓等）。知らせには、係が
作業空間・GitHub を調べた事実（reply_facts：提出・--no-check・未コミット・持ち場の外の変更 等）と、作業役が返答の最後に書く
状態の行を照らした注意を先頭に書く。
進行役の頼みで起動する作業役は、係がアプリ用の起動（画面なし。ecobuild_agent.app）で持つ。人は引き取って（takeover）
対話型で続け、返せる（handback）。

進行役はチームの様子（作業中・待機中・止まっている。team）を見て、止まった・迷った作業役を起動し直せる（restart_plan。
作業空間・ブランチ・作業はそのまま。新しい会話か、続きから）。頼みの途中経過は係が書き（PROGRESS）、頼んだ側は
それを見ながら待つ（係が止まれば、すぐに分かる）。
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import ecobuild_container as container
from ecobuild import settings as _settings
from ecobuild.errors import EcoBuildError
from ecobuild.fsutil import locked, remove_tree

from . import status as agent_status
from .errors import ErrorCode

LEAD, MANAGER, WORKER = "lead", "manager", "worker"
ROLES = (LEAD, MANAGER, WORKER)
ROLE_NAMES = {LEAD: "進行役", MANAGER: "管理役", WORKER: "作業役"}
ROLE_HINT = "lead（進行役）・manager（管理役）・worker（作業役）です。"
LEADING = (LEAD, MANAGER)   # 自分ではファイルを編集せず、下に任せる役（書けるのは .ecobuild/ai の中だけ）
UP_NAMES = ("lead", "進行役", "上")   # agent team send の宛先：自分を作った（上の）役
TEAM_AREA = ".ecobuild/ai/team"     # 進行役の作業空間の中の、作業役（と下の進行役）の作業空間の置き場所
MEMBER_FILE = ".ecobuild/ai/member.json"   # 作業役の作業空間の中：役・名前・タスク・進行役の場所・モデル
BRIEF_FILE = ".ecobuild/ai/brief.md"       # 任された仕事（進行役の指示）
REPORT_FILE = ".ecobuild/ai/report.md"     # 作業役の報告
MODULE_PLACE_FILE = ".ecobuild/ai/module-lead.json"   # モジュールの進行役の作業空間の印（ecobuild_agent.facilitator が置く）
PLAN_FILE = ".ecobuild/ai/plan.md"         # 進行役の計画
MODEL_KEYS = {LEAD: "agent_lead_model", MANAGER: "agent_manager_model", WORKER: "agent_worker_model"}   # このPCの設定：役ごとのモデル
DEFAULT_MODELS = {MANAGER: "opus", WORKER: "sonnet"}   # 設定がないときの役のモデル（進行役は Claude Code の既定）
REQUESTS = "requests"               # 状態の置き場所の中の、頼みの置き場所
WINDOW_VARIABLE = "ECOBUILD_AGENT_WINDOW"   # GUI のエージェントの窓の端末で 1（頼みを係に渡す）
REQUEST_TIMEOUT = 1800              # 頼みの結果を待つ秒数（clone・イメージ作り込みで長くかかることがある）
STALL_SECONDS = 120                 # 頼みを実行する ecobuild が、この秒数なにも経過を出さなければ止まったとみなす（係が止める）
PROGRESS = ".progress"              # 頼みの置き場所の中：<id>.progress（係が書く途中経過。係が動いている間は毎秒。
                                    # .json にしない：頼み〔<id>.json〕と取り違える）
SERVE_SILENT = 30                   # 途中経過がこの秒数書かれなければ、係が止まったとみなす
SERVE_BEAT = "serve.alive"          # 頼みの置き場所の中：係が動いている印（BEAT_EVERY 秒ごと。.json にしない）
BEAT_EVERY = 5
BEAT_STALE = 20                     # 印がこの秒数より古ければ、頼まずに（待たずに）止める
FIRST_PROMPT = {
    WORKER: f"{BRIEF_FILE} に任された仕事があります。読んで作業を始めてください。終わったら {REPORT_FILE} に報告を書き、提出してください。"
            "時間のかかる実行（test・build・check・submit）は前面で動かし、結果を待つために返答を終えないでください。"
            "返答の最後は「状態：…」の行です。",
    MANAGER: f"{BRIEF_FILE} に上の役（進行役、または管理役）から任された仕事があります。読んだら、まず自分では調べずに、観点を分けて作業役に一度に任せ、"
             "報告を読んで計画を進めてください。",
    LEAD: f"{BRIEF_FILE} に任された部分があります。読んで、ユーザーとの話を進めてください。",
}
PROGRESS_FILE = ".ecobuild/ai/progress.md"   # 作業役の途中経過（区切りごとに書く。起動し直したときに読む）
REPORT_ONLY_PROMPT = (f"{BRIEF_FILE} に任された仕事があります（報告だけの仕事です：ファイルを変えず・コミットせず・提出しません）。"
                      f"読んで調べ、結果を {REPORT_FILE} に書き、`ecobuild agent report` で管理役に知らせてください。"
                      "返答の最後は「状態：…」の行です。")
RESTART_PROMPT = {   # 起動し直した（新しい会話）ときの最初の発言
    WORKER: "管理役があなたを起動し直しました（前の会話は引き継いでいません）。次の順で確かめてから続けてください："
            f"①{BRIEF_FILE}・{PROGRESS_FILE}（前の会話の途中経過） ②`ecobuild task status` と `ecobuild log --count 10` "
            f"③{REPORT_FILE}・git の状態（未コミットの変更） "
            "④前の会話で待っていたもの（テスト・ビルド等）があれば、その結果を自分で確かめる ⑤残りを進める。"
            "最初の返答に、どこまで進んでいたかを1〜2行で書き、返答の最後は「状態：…」の行にしてください。",
    MANAGER: f"上の役があなたを起動し直しました（前の会話は引き継いでいません）。{BRIEF_FILE}・{PLAN_FILE}・チームの様子"
             "（agent team list）から、どこまで進んでいるかを確かめてから続けてください。自分で調べずに、残りの調べは作業役に任せてください。",
    LEAD: f"上の役があなたを起動し直しました（前の会話は引き継いでいません）。{BRIEF_FILE}・{PLAN_FILE}・チームの様子"
          "（agent team list）から、どこまで進んでいるかを確かめてから続けてください。",
}
RESUME_PROMPT = ("上の役があなたを起動し直しました（この会話の続きです）。止まっていたところから続けてください。"
                 "待っていた結果があれば先に確かめ、返答の最後は「状態：…」の行にしてください。")


@dataclass(frozen=True)
class Member:
    """チームの1人（進行役が作った作業役・進行役）。"""
    name: str
    role: str
    path: Path
    task: int
    branch: str = ""
    model: str = ""
    lead: str = ""              # 作った進行役の作業空間（このPCの場所）
    owner: str = ""             # 作った会話（Claude Code のセッションの ID。役に依らない。空なら前の記録：どの会話にも見える）
    reported: bool = False      # 報告（REPORT_FILE）がある
    prompt: str = ""            # 起動するときの最初の発言（作ったとき・起動し直すときだけ）
    opened: bool = False        # 新しい画面で起動した（係・GUI が開くときは False）
    agent: str = ""             # 起動するコマンド（起動し直すときだけ。続きからなら claude --resume <会話>）
    state: str = ""             # 様子（agent_status.activity：working・idle・stopped・unknown）
    since: float | None = None  # その様子になった時刻
    last_reply: str = ""        # 最後の返答の頭
    context: float | None = None   # コンテキストの使用率
    waiting: int = 0            # 受け箱にあって、まだ届いていないもの（言付け等）
    mode: str = ""              # 起動のしかた（app：係が持つアプリ用の起動。空なら対話型か、動いたことがない）
    doing: str = ""             # 今していること（アプリ用：最後に使った道具。「Bash：ecobuild test」）
    doing_at: float | None = None  # その時刻
    usage: dict | None = None   # 最後の返答の使用量（アプリ用。トークン・費用・時間）
    limits: dict | None = None  # 使用量の制限（アプリ用。five_hour・seven_day の used_percentage・resets_at）
    error: str = ""             # 止めていないのに終わった（アプリ用。終了コード・標準エラーの末尾）
    app: bool = False           # 係がアプリ用で起動した（team start・restart の結果）
    note: str = ""              # 起動できなかったわけ等
    message_id: str = ""        # 送った言付けの番号（send の結果だけ）


@dataclass(frozen=True)
class Team:
    lead: Path
    members: tuple[Member, ...]


def model_for(role: str) -> str:
    """このPCの設定の、役のモデル（設定がなければ DEFAULT_MODELS、空と書けば Claude Code の既定）。"""
    return _settings.load_config().get(MODEL_KEYS[role], DEFAULT_MODELS.get(role, "")).strip()


OWNER_VARIABLE = "CLAUDE_CODE_SESSION_ID"   # Claude Code が道具に渡す、いまの会話の ID


def owner_session() -> str:
    """いまの会話（この ecobuild を呼んだ Claude Code のセッション）の ID。分からなければ空。"""
    return os.environ.get(OWNER_VARIABLE, "").strip()


def mine(recorded: str, owner: str | None) -> bool:
    """記録の持ち主 recorded の分が、会話 owner から見えるか（owner が空＝区別しない、記録が空＝前の記録）。"""
    return not owner or not recorded or recorded == owner


def member_info(root: Path) -> dict:
    """作業空間 root が作業役・下の進行役なら、その記録（なければ空）。"""
    try:
        data = json.loads((Path(root) / MEMBER_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def is_module_place(root: Path) -> bool:
    """root がモジュールの進行役の作業空間か（タスクを持たない。印 MODULE_PLACE_FILE）。"""
    return (Path(root) / MODULE_PLACE_FILE).is_file()


def role_of(root: Path, chosen: str = "") -> str:
    """作業空間 root のエージェントの役：指定（chosen）、なければ記録（member.json）、なければ進行役（記録のない作業空間＝
    人が起動するトップ）。"""
    if is_module_place(root):   # モジュールの進行役の作業空間：進行役だけ
        if chosen and chosen != LEAD:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "ここはモジュールの進行役の作業空間です。ほかの役は起動しません。",
                                hint="管理役は、進行役が agent team start --manager で作ります。")
        return LEAD
    role = chosen or member_info(root).get("role") or LEAD
    if role not in ROLES:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"役 {role!r} はありません。", hint=ROLE_HINT)
    return role


ROLES_FILE = ".ecobuild/ai/roles.json"   # 作業空間の中：会話（Claude Code のセッションの ID）→ 役（再開しても同じ役に）
RESUME_FLAGS = ("--resume", "-r")
CONTINUE_FLAGS = ("--continue", "-c")


def remembered_roles(root: Path) -> dict:
    try:
        data = json.loads((Path(root) / ROLES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def remember(root: Path, session: str, role: str) -> None:
    """会話 session の役を覚える（.ecobuild/ai の中：コミットしない）。"""
    roles = {**remembered_roles(root), session: role}
    path = Path(root) / ROLES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(list(roles.items())[-500:]), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def resumed_session(command: tuple[str, ...], latest) -> str | None:
    """command が続きからの起動なら、その会話の ID（--resume <id>。--continue なら latest() ＝ いちばん新しい会話）。
    続きからでなければ None、続きからだが分からなければ ""。"""
    if command[:1] != ("claude",):
        return None
    for index, word in enumerate(command):
        if word in RESUME_FLAGS:
            following = command[index + 1] if index + 1 < len(command) else ""
            return "" if not following or following.startswith("-") else following   # 値なし：Claude の一覧で選ぶ
        if word.startswith("--resume="):
            return word.split("=", 1)[1]
        if word in CONTINUE_FLAGS:
            return latest() or ""
    return None


def new_session(root: Path, role: str, command: tuple[str, ...]) -> tuple[str, ...]:
    """新しい会話なら、ID を決めて渡し（--session-id）、その役を覚える。続きから・ID 指定済み・Claude Code でなければそのまま。"""
    if command[:1] != ("claude",) or any(w in command or any(x.startswith(w + "=") for x in command)
                                         for w in (*RESUME_FLAGS, *CONTINUE_FLAGS, "--session-id")):
        return command
    session = str(uuid.uuid4())
    remember(root, session, role)
    return (*command, "--session-id", session)


def agent_options(root: Path, role: str, command: tuple[str, ...]) -> tuple[str, ...]:
    """Claude Code に足す引数：モデル（記録、なければこのPCの役の設定。指定済みなら足さない）。進行役が書ける場所は
    フック（status の lead-edit）で決める（道具ごと禁じると、計画・任せる内容を Bash で書く抜け道を使った）。"""
    if command[:1] != ("claude",):
        return command
    model = member_info(root).get("model") or model_for(role)
    extra = []
    if model and "--model" not in command:
        extra += ["--model", model]
    return (*command, *extra)


RETRY_WAIT = (2, 4, 8)   # GitHub の一時的な失敗（5xx・接続）のとき、作り直す前に待つ秒数（回数＝長さ）
_TRANSIENT = re.compile(r"HTTP 5\d\d|Bad Gateway|Service Unavailable|Gateway Time-?out|timed? ?out|"
                        r"connection (?:reset|refused|aborted|closed)|could not resolve host|unexpected EOF|"
                        r"TLS handshake|network is unreachable", re.IGNORECASE)


def transient(error: Exception) -> bool:
    """GitHub・ネットワークの一時的な失敗か（待ってやり直せば通るもの）。"""
    return bool(_TRANSIENT.search(_message(error)))


def create(module, name: str, brief: str, *, role: str = WORKER, model: str = "", existing: int = 0,
           report_only: bool = False, progress=lambda message: None, wait=None) -> Member:
    """進行役の作業空間 module に、チームの1人を作る：子タスク（題名 name・本文 brief）と、そのタスクブランチを置いた
    作業空間（TEAM_AREA/<番号>-<名前>）。任された仕事・記録を作業空間の .ecobuild/ai に置く。起動はしない。
    existing：子タスクを新しく作らず、この番号の開いた子タスクから作る（作業空間だけがない子タスク 等）。
    report_only：報告だけの作業役（調べもの・レビュー。提出しない：任せる仕事に NO_SUBMIT を書き、最初の発言・決まりを替える）。

    何人も並べて作れる（係が並べて実行する）。同じ名前を同時には作らない（後のものは止める）。前に作りかけて止まった
    もの（開いた子タスク・作業空間のフォルダー）が残っていれば、それを片付けて続きから作る（二重に作らない）。
    GitHub の一時的な失敗（transient）は、待って（RETRY_WAIT）やり直す（作った子タスクはそのまま使う）。途中で
    失敗したら、作りかけを片付けて（作業空間を消し、この回に作った子タスクを閉じて）、何が残ったかを失敗に書く。"""
    wait = wait or time.sleep
    from ecowork import model as _work
    if role not in ROLES:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"役 {role!r} はありません。", hint=ROLE_HINT)
    if role == LEAD:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "進行役は、ユーザーが起動するものです（作れません）。",
                            hint="進行役の下には仕事ごとに管理役（--manager）を作り、作業役は管理役が作ります。")
    mine = role_of(module.root)
    if mine == LEAD and role == WORKER:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "進行役は、作業役を直接作りません（仕事ごとに管理役を作り、管理役に命令します）。",
                            hint="agent team start <名前> --manager --brief … で管理役を作ってください。")
    if mine == WORKER:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "作業役は、作業役・管理役を作りません。",
                            hint=f"分けたいときは、{REPORT_FILE} に分け方の提案を書いて管理役に伝えてください（管理役が作ります）。")
    label = _work.check_branch_label(name)
    if name.isdigit():   # 番号だけの名前は、別の人の子タスクの番号と取り違える（send・close 等は番号でも探す）
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"名前「{name}」は番号だけです。",
                            hint="子タスクの番号と取り違えないよう、文字を入れた名前にしてください。")
    if not brief.strip():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "任せる仕事（--brief）が空です。",
                            hint="目的・返してほしいもの・使ってよい道具・範囲（やらないこと）を書いてください。")
    if report_only and role != WORKER:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "報告だけ（--report-only）にできるのは作業役だけです。")
    if report_only and NO_SUBMIT not in brief:
        brief = brief.rstrip() + f"\n\n（ECOBuild より：この仕事は報告だけです。**{NO_SUBMIT}**）\n"
    # モジュールの進行役はタスクを持たない：管理役には親のないタスク（作成元から）を作る
    lead_task = None if is_module_place(module.root) else module.require_task_branch(f"{ROLE_NAMES[role]}の作成")
    parent = lead_task.number if lead_task else None
    if existing and parent is None:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "モジュールの進行役では、既にあるタスク（--task）は使えません。",
                            hint="管理役は新しいタスクで作ります（--task を外してください）。")
    module.prepare_agent_area()   # 進行役の側の git に、作業空間の置き場所を見せない（除外）
    with _creating(module, name):
        task = _given_child(module, parent, existing) if existing else None
        task = task or _leftover(module, parent, name, progress)
        created = task is None
        if created:
            task = _new_child(module, parent, name, brief, role, progress, wait)
        directory = module.root / TEAM_AREA / f"{task.number}-{label}"
        for attempt in range(len(RETRY_WAIT) + 1):
            try:
                return _prepare(module, task.number, directory, name, label, brief, role, model, progress,
                                lead_task=lead_task, report_only=report_only)
            except Exception as error:
                if transient(error) and attempt < len(RETRY_WAIT):   # 作りかけ（作業空間・ブランチ）を片付けて、やり直す
                    _clean_up(module, task.number, directory, name, error, close=False, branch=created)
                    progress(f"GitHub の一時的な失敗です（{_message(error)}）。{RETRY_WAIT[attempt]}秒待ってやり直します…")
                    wait(RETRY_WAIT[attempt])
                    continue
                left = _clean_up(module, task.number, directory, name, error, close=created)
                raise _failed(error, name, role, left, task, resumed=not created, directory=directory) from error


def _new_child(module, parent: int | None, name: str, brief: str, role: str, progress, wait):
    """子タスクを作る（parent がなければ親のないタスク：モジュールの進行役の管理役）。一時的な失敗は、できていればそれを使い、
    できていなければ待ってやり直す。"""
    for attempt in range(len(RETRY_WAIT) + 1):
        progress(f"{'タスク' if parent is None else '子タスク'}「{name}」を作っています…")
        try:
            if parent is None:
                return module.repository.create_task(name, body=brief)
            return module.repository.create_task(name, body=brief, parent=parent)
        except Exception as error:   # 作った後の読み直し等で失敗したもの：子タスクはできていることがある
            try:
                made = _open_child(module, parent, name)
            except Exception:
                made = None
            if made is not None and transient(error):
                progress(f"子タスク #{made.number} はできています（{_message(error)}）。続けます…")
                return made
            if made is None and transient(error) and attempt < len(RETRY_WAIT):
                progress(f"GitHub の一時的な失敗です（{_message(error)}）。{RETRY_WAIT[attempt]}秒待ってやり直します…")
                wait(RETRY_WAIT[attempt])
                continue
            raise _failed(error, name, role, made and _close_child(module, made.number, name, error), made) from error


def _given_child(module, parent: int, number: int):
    """--task の子タスク：親 parent の開いた子タスクで、まだ作業空間がないもの。"""
    if any(member.task == number for member in team(module.root).members):
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"子タスク #{number} には、もう作業空間があります。",
                            hint="agent team list で確かめてください。")
    for issue in module.repository.github.sub_issues(module.root, parent):
        if issue.number == number and issue.state == "open":
            return issue
    raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"#{number} は、このタスク（#{parent}）の開いた子タスクではありません。",
                        hint="作業空間のない子タスクは agent team list --orphans で分かります。")


def orphans(module, owner: str | None = None) -> list[dict]:
    """進行役のタスクの開いた子タスクのうち、作業空間（チームの1人）がないもの（作りかけで止まった等。GitHub に聞く）：
    [{task, title}]。agent team start <名前> --task <番号> で作業空間を作れる。"""
    lead_task = module.require_task_branch("子タスクの一覧")
    numbers = {member.task for member in team(module.root).members}
    return [{"task": issue.number, "title": issue.title}
            for issue in module.repository.github.sub_issues(module.root, lead_task.number)
            if issue.state == "open" and issue.number not in numbers]


def _prepare(module, number: int, directory: Path, name: str, label: str, brief: str, role: str, model: str,
             progress, *, lead_task=None, report_only: bool = False) -> Member:
    """子タスク number の作業空間 directory を作り、任された仕事・記録を置く。記録には、作った役（lead：このPCの場所。
    作業役はコンテナの中で動くので、中からは読めない）の子タスク・ブランチ・名前も書く（作業役が自分の上を知る）。"""
    from ecobuild import workspaces as _workspaces
    progress(f"子タスク #{number} の作業空間を用意しています（clone・依存先）…")
    member_module = module.start_task_in(number, directory, name=label)
    progress("作業空間ができました。任せる仕事を置いています…")
    _workspaces.record_quietly(member_module.root)
    _inherit_container(module.root, member_module.root)
    member_module.prepare_agent_area()
    (member_module.root / BRIEF_FILE).write_text(brief.rstrip() + "\n", encoding="utf-8", newline="\n")
    up = member_info(module.root)
    info = {"role": role, "name": name, "task": number, "lead": str(module.root), "model": model.strip(),
            "owner": owner_session(), "lead_role": up.get("role") or LEAD, "lead_name": up.get("name") or module.root.name,
            "lead_task": getattr(lead_task, "number", 0), "lead_branch": getattr(lead_task, "branch", ""),
            "lead_readable": False, **({"report_only": True} if report_only else {})}
    # 記録（MEMBER_FILE）は最後に置く：あれば作り終えた作業空間（なければ作りかけ。_leftover）
    (member_module.root / MEMBER_FILE).write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    branch = member_module.repository.git.current_branch() or ""
    return Member(name, role, member_module.root, number, branch, model.strip(), str(module.root),
                  prompt=REPORT_ONLY_PROMPT if report_only else FIRST_PROMPT[role])


CREATING = "ecobuild-team"   # 進行役の clone の git の場所の中：作っている名前ごとのロック（<名前>.lock）


@contextmanager
def _creating(module, name: str):
    """同じ名前を同時に作らない（作っている間ロックを持つ。係が止めたプロセスのロックは OS が外す）。"""
    folder = module.root / module.repository.git.output("rev-parse", "--git-path", CREATING)
    try:
        with locked(folder / f"{name}.lock", wait=False):
            yield
    except BlockingIOError:
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"「{name}」は今、別の頼みで作っている途中です。",
                            hint="同じ名前を2回頼んでいます。終わるのを待って agent team list で確かめてください。") from None


def _leftover(module, parent: int, name: str, progress):
    """同じ名前の前の作りかけ：開いた子タスク（作業空間の記録 MEMBER_FILE がないもの）があれば、その Issue（続きから作る）。
    同じ名前の記録のない作業空間のフォルダーは消す（中に変更があれば止める）。もうチームにいれば止める。"""
    from ecowork.git import Git
    if any(member.name == name for member in team(module.root).members):
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"チームにはもう「{name}」がいます。",
                            hint="続けさせるなら agent team send・restart、作り直すなら agent team close で閉じてから。"
                                 "別の仕事なら別の名前にしてください。")
    area = module.root / TEAM_AREA
    for folder in sorted(area.glob(f"*-{name}")) if area.is_dir() else ():
        number, _, label = folder.name.partition("-")
        if not folder.is_dir() or member_info(folder) or not number.isdigit() or label != name:   # 「ログイン-画面」は別の名前
            continue
        if (folder / ".git").exists():
            try:
                tree = Git(folder).working_tree()
            except Exception:   # 壊れた clone（clone の途中で止まった）
                tree = None
            if tree is not None and not (tree.clean and tree.ahead == 0):
                raise EcoBuildError(ErrorCode.ALREADY_EXISTS,
                                    f"「{name}」の作りかけの作業空間 {TEAM_AREA}/{folder.name} に、変更があります。",
                                    hint="消してよいか分からないので止めました。ユーザーに伝えて決めてもらってください。")
        progress(f"前の作りかけの作業空間 {TEAM_AREA}/{folder.name} を片付けています…")
        remove_tree(folder)
    found = _open_child(module, parent, name)
    if found is not None:
        progress(f"前の作りかけの子タスク #{found.number} の続きから作ります…")
    return found


def _open_child(module, parent: int | None, name: str):
    """親タスク parent の、題名 name の開いた子タスク（いちばん新しいもの。なければ None）。親がなければ（モジュールの
    進行役が作る管理役のタスク）探さない：同じ題名の、人が作ったタスクを取り違えない。"""
    if parent is None:
        return None
    children = [issue for issue in module.repository.github.sub_issues(module.root, parent)
                if issue.title == name and issue.state == "open"]
    return max(children, key=lambda issue: issue.number) if children else None


def _clean_up(module, number: int, directory: Path, name: str, error: Exception, *, close: bool,
              branch: bool | None = None) -> list[str]:
    """作りかけを片付ける：作業空間 directory を消し、close なら子タスク number を閉じる。branch（省けば close と同じ）なら
    この回に置いたタスクブランチも消す。片付けられなかったもの（文）を返す。"""
    from ecowork import model as _work
    from ecowork.git import Git
    left = []
    if (close if branch is None else branch) and (directory / ".git").exists():
        branch = _work.task_branch_name(number, directory.name.split("-", 1)[1])
        try:
            git = Git(directory)
            if git.has_remote_branch(branch):   # この回に作って push したもの（まだ何もコミットしていない）
                git.push_delete(branch)
        except Exception as problem:
            left.append(f"GitHub のタスクブランチ {branch}（消せませんでした：{_message(problem)}）")
    if directory.exists():
        try:
            remove_tree(directory)
        except OSError as problem:
            left.append(f"作業空間 {TEAM_AREA}/{directory.name}（消せませんでした：{problem}）")
    if close:
        left += _close_child(module, number, name, error)
    return left


def _close_child(module, number: int, name: str, error: Exception) -> list[str]:
    """作りかけの子タスクを「対応しない」として閉じる（理由をコメントに。消さない）。閉じられなければ、その文。"""
    tracker = module.repository.tracker
    try:
        tracker.comment(number, f"ECOBuild：「{name}」の作成が途中で失敗したため閉じます（{_message(error)}）。")
    except Exception:
        pass   # 閉じるのを優先する
    try:
        tracker.close(number, not_planned=True)
    except Exception as problem:
        return [f"子タスク #{number}（開いたまま：{_message(problem)}）"]
    return []


def _failed(error: Exception, name: str, role: str, left, task, *, resumed: bool = False,
            directory: Path | None = None) -> EcoBuildError:
    """作成の失敗を、何が残ったか・どうすればよいかを添えて伝える。left：片付けられなかったもの（task がなければ None）。
    details の頭に、子タスクの番号と作業空間が残っているかを書く（頼んだ側・ログで分かるように）。"""
    hint = getattr(error, "hint", None)
    still = resumed or any(item.startswith(f"子タスク #{task.number}") for item in left or ()) if task is not None else False
    made = ["子タスク：なし" if task is None else f"子タスク：#{task.number}（{'開いたまま' if still else '閉じた'}）",
            f"作業空間：残っている（{directory.as_posix()}）" if directory is not None and directory.exists() else "作業空間：なし"]
    details = getattr(error, "details", None)
    if task is None:
        after = "子タスクはできていません（できていれば、task list で確かめて閉じてください）。"
    elif left:
        after = ("片付けられなかったもの：" + "、".join(left) + "。もう一度 start すると、残った作りかけを片付けて"
                 "続きから作ります（子タスクが閉じていれば新しく作ります）。")
    elif resumed:
        after = f"作りかけの作業空間を消しました。子タスク #{task.number}（前の作りかけ）は開いたままです。もう一度 start してください。"
    else:
        after = f"子タスク #{task.number} は閉じ、作りかけの作業空間も消しました。もう一度 start してください。"
    return EcoBuildError(getattr(error, "code", None) or ErrorCode.AGENT_ERROR,
                         f"{ROLE_NAMES[role]}「{name}」を作れませんでした：{_message(error)}",
                         hint=after + (f"\n{hint}" if hint else ""),
                         details=[*made, *(details if isinstance(details, (list, tuple)) else [details] if details else [])])


def _message(error: Exception) -> str:
    return getattr(error, "message", None) or str(error) or type(error).__name__


def _inherit_container(lead: Path, member: Path) -> None:
    """進行役の作業空間のコンテナの選択（コンテナにするか・使うイメージ・使わせないもの）を、作業役の作業空間にも。
    作業役も同じように隔離して確認なしで動かす（新しい clone はコンテナにしていないので、そのままではこのPCで動き、
    初めてのフォルダーの確認で止まる）。"""
    from ecobuild import config as _config
    from .inside import DENY_KEY
    chosen = {key: value for key, value in _config.load_local(lead).items()
              if key in (container.KEY, container.IMAGE_KEY, DENY_KEY)}
    if chosen:
        _config.save_local(member, {**_config.load_local(member), **chosen})


def team(root: Path, owner: str | None = None) -> Team:
    """進行役の作業空間 root のチーム（TEAM_AREA の下の作業空間）。
    owner：会話の ID を渡すと、その会話が作った分だけ（同じ作業空間の別の会話の分を混ぜない）。省けば全員。"""
    from ecowork.git import Git
    found = []
    area = Path(root) / TEAM_AREA
    for folder in sorted(area.iterdir()) if area.is_dir() else ():
        info = member_info(folder)
        if not info or not mine(str(info.get("owner") or ""), owner):
            continue
        try:
            branch = Git(folder).current_branch() or ""
        except Exception:   # 壊れた clone 等。場所だけ出す
            branch = ""
        seen = agent_status.activity(inbox_of(folder))
        found.append(Member(str(info.get("name", folder.name)), str(info.get("role", WORKER)), folder,
                            int(info.get("task") or 0), branch, str(info.get("model") or ""), str(info.get("lead") or ""),
                            str(info.get("owner") or ""), (folder / REPORT_FILE).is_file(), state=seen["state"], since=seen["since"],
                            last_reply=seen["last_reply"], context=seen["context"], waiting=seen["waiting"],
                            mode=seen.get("mode", ""), doing=seen.get("doing", ""), doing_at=seen.get("doing_at"),
                            usage=seen.get("usage"), limits=seen.get("limits"), error=seen.get("error", "")))
    return Team(Path(root), tuple(found))


def restart_plan(root: Path, name: str, *, resume: bool = False) -> Member:
    """チームの1人（name）を起動し直すときの起動のしかた（作業空間・ブランチ・作業はそのまま。止めるのは呼ぶ側）。
    resume：前の会話の続きから（Claude Code の --resume。会話が分からなければ止める）。そうでなければ新しい会話で、
    どこまで進んだかを確かめてから続けさせる。"""
    member = find(root, name)
    if not resume:
        return Member(**{**member.__dict__, "prompt": RESTART_PROMPT.get(member.role, RESTART_PROMPT[WORKER])})
    session = agent_status.session_of(inbox_of(member.path))
    if not session:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"「{member.name}」の前の会話が分かりません。",
                            hint="--resume なしで、新しい会話で起動し直してください（作業空間の作業はそのままです）。")
    return Member(**{**member.__dict__, "prompt": RESUME_PROMPT, "agent": f"claude --resume {session}"})


def describe_activity(member: dict, now: float | None = None) -> str:
    """様子の1行（team list の表示）：作業中（12分）・待機中・止まっている、と届いていない言付け・コンテキスト。"""
    now = time.time() if now is None else now
    state = member.get("state") or ""
    text = agent_status.STATE_NAMES.get(state, "")
    if not text:
        return ""
    since = member.get("since")
    if isinstance(since, (int, float)) and state in (agent_status.WORKING, agent_status.IDLE):
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


def find(root: Path, name: str, owner: str | None = None) -> Member:
    """チームの1人を名前（か番号・フォルダー名）で探す。owner：会話の ID（その会話が作った分だけから）。
    2人以上に合えば（ある人の名前が別の人の番号 等）、取り違えないよう候補を出して止める。"""
    found = [member for member in team(root, owner).members if name in (member.name, str(member.task), member.path.name)]
    if len(found) == 1:
        return found[0]
    if found:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"「{name}」に合う人が {len(found)} 人います。",
                            hint="フォルダー名（<番号>-<名前>）で指してください。",
                            details=[f"{ROLE_NAMES.get(m.role, '作業役')}「{m.name}」 #{m.task}  {TEAM_AREA}/{m.path.name}"
                                     for m in found])
    raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"チームに「{name}」はいません。",
                        hint="ecobuild agent team list で一覧を見られます。")


def briefing(root: Path, role: str, program: str) -> list[str]:
    """起動のときにエージェントへ渡す、役ごとの決まり（Anthropic のマルチエージェントの教訓に沿う）。"""
    info = member_info(root)
    if role == LEAD:
        return _lead_briefing(program) + (module_lead_briefing(program) if is_module_place(root) else [])
    if role == MANAGER:
        up = ROLE_NAMES.get(info.get("lead_role"), ROLE_NAMES[LEAD])   # 作った上の役：進行役、または管理役（下の管理役のとき）
        upper = "進行役（ユーザーと話す役）" if up == ROLE_NAMES[LEAD] else f"上の管理役「{info.get('lead_name') or '?'}」"
        lines = [
            "## あなたの役：管理役",
            "",
            f"あなたは管理役です。1つの仕事を受け持ちます。{upper}から命令を受け、仕事を分けて作業役（大きな部分は下の管理役）に任せ、"
            "結果を読んで取り込みます。"
            f"ユーザーとは直接話しません（ユーザーへの質問・報告は{up}へ send で渡し、{up}が取り次ぎます）。"
            f"作業役の返答の終わり・報告の知らせは、{up}ではなくあなたに届きます。"
            f"**書けるのは `{PLAN_FILE.rsplit('/', 1)[0]}/` の中だけで、書くには Edit・Write の道具を使います**（計画・任せる内容の下書き。"
            "Bash の python・sed・リダイレクト・heredoc では、中でも書きません）。Claude Code の記憶（メモリ）には書けません。"
            f"残したいことは {PLAN_FILE} に書きます。コード・文書を書く・直すのは作業役です。",
            "**ECOBuild の手順を外れることは、ユーザーの了承なしに決めない・指示しない**：確認を省く（`--no-check`）、"
            "ビルド・テストを ECOBuild のコマンドの代わりに直接動かす、等。環境の問題で手順どおりに進められないときは、"
            f"作業役を止めて待たせ、{up}経由でユーザーに伝えて決めてもらいます（答えを待たずに進めると決めない）。",
            "聞かずに自分で決めること：直し方・仕事の分け方・作業役の人数と名前・順番・モデル・"
            "レビューの回数・取り込む／直しを頼む（注意がないとき）。迷ったら「間違えたら戻せるか」で分け、戻せるなら決めて進め、"
            f"理由を計画に1行書いて{up}に一言伝えます。{up}に聞くこと（{up}がユーザーに取り次ぎます）：目的・優先順位・範囲、"
            "ECOBuild の手順を外すこと、元に戻せない・外に出る操作、費用や時間が大きく変わること。選択肢を並べて「どれにしますか」とは"
            "聞きません（これで進めます、違えば言ってください、と決めて伝えます）。",
            "",
            "### 最初の動き",
            "**自分では調べも作業もしません。仕事を受けたら、まず観点で分けて、同時に作業役へ任せます。**",
            f"- 任せる前にしてよいのは、{up}の命令・`{BRIEF_FILE}`・`{program} task status`・`{program} agent team list`・"
            "報告を読む・計画を書くことだけです。コード・文書・ログ・記事を開いて調べるのは、任せる前でも「調べもの」です。"
            "読みたくなったら、それを調べものとして任せます。理由：あなたの会話は長く続きます。調べでコンテキストを使うと、"
            f"{up}とのやりとりと全員のまとめが後で苦しくなります。",
            "- 調べものは観点を変えて（対象の別・見る角度・資料の別）、観点の数だけ並べて任せます（1人にまとめません）。"
            "`--report-only` を付けて（報告だけ・提出しない作業役になります）、--brief に「要点を先頭に、短く」と書きます。"
            "報告が揃うまで、同じ所を自分で読みません。",
            "- 関係のある仕事も分けます。部分どうしの接点（名前・形式・触ってよい場所・渡すもの）を先に計画に書き、全員の --brief に"
            "同じ文で写せば、並べて任せられます。接点が決まらないときは、それを決める調べものだけを先に任せ、報告を読んでから残りを並べます。",
            "- 作業役から見えるのは、自分の作業空間と GitHub だけです。渡すものは --brief・send の本文か、Issue のコメント"
            f"（`{program} task comment`）に書きます。自分の作業空間のパスで指さない（作業役には見えません）。",
            "",
            "### 進め方",
            f"1. まず {PLAN_FILE} に計画を書きます（目的・分け方・順番・誰に何を任せたか）。話が長くなっても、ここを見れば続けられるように更新し続けます。",
            f"2. 任せるときは `{program} agent team start <名前> --brief <任せる内容>` で作業役を作ります（子タスクと、その作業空間ができ、"
            "作業役は ECOBuild の係が画面なしで動かし始めます。タブ・画面は開きません）。<名前> はタスクブランチの名前にもなる短い名前です。"
            f"作業空間・子タスクは、`agent team start` が一式（子タスク・作業空間・タスクブランチ）で作ります。**自分では作りません**"
            f"（`{program} workspace create`・`{program} task new` は使いません）。自分で作ると二重・食い違いになります。",
            "   --brief には必ず次を書きます：**目的**（何のためか）、**返してほしいもの**（報告に書くこと・提出の形）、"
            "**使ってよい道具・見る場所**、**範囲**（やらないこと・触らないファイル）。短い指示は取り違え・重複のもとです。",
            f"   変えてよいファイルは `## {AREA_HEADING}`、触らないファイルは `## {KEEP_OUT_HEADING}` の節に、1行に1つのパス"
            "（フォルダー・ファイル・`src/ui/*.py` のような glob）の箇条書きで書きます。ECOBuild がこれと作業役の変更を照らして、"
            "外のファイルを変えたら知らせます（この形でなければ照らしません）。",
            "   何人も作るときは、1人ずつ終わるのを待たずに並べて頼みます（1人に数十秒かかるので、順に待つと全員そろうまで"
            f"長くかかります）：任せる内容を1人1ファイル（ファイル名＝名前。`{PLAN_FILE.rsplit('/', 1)[0]}/briefs/画面.md` 等）に"
            f"書き、`{program} agent team start --brief-dir <フォルダー>` で一度に作ります（数人ずつ並べて作ります）。"
            "同じ名前は2回頼みません。",
            "   作成が途中で失敗したときは、ECOBuild が作りかけ（作業空間・子タスク）を片付け、何が残ったかを失敗の文に書きます。"
            "その文に従ってもう一度 start します（残った作りかけがあれば、それを片付けて続きから作ります。二重にはなりません）。"
            f"子タスクだけができて作業空間がないものは `{program} agent team list --orphans` で分かり、"
            f"`{program} agent team start <名前> --task <番号>` で作業空間を作れます。",
            "3. 作業役の人数は、独立に進められる部分の数で決めます。分けられるか迷ったら、まず分ける側で考えます"
            "（小さなことだけ、任せずにユーザーと話すのでも構いません）。計画を書いたら、最初の1人を待たずに、分ける部分を全部一度に "
            "start します（run_in_background で並べる）。同じファイルを2人に任せません（持ち場を分ける）。ある結果がないと始められない"
            "仕事、または同じファイルに触る仕事だけ、順に任せます（先に1人が分けやすい形に下ごしらえしてから並べてもよい）。",
            "4. 任せたら**作業役を待ちます**（自分で作業を始めない）。作業役の返答が終わると、ECOBuild がこの会話に知らせます。"
            "知らせの1行目は ECOBuild が作業空間・GitHub を調べた注意（完了と言うのに提出がない・--no-check で提出・"
            "持ち場の外の変更・未コミットの変更 等）、次の行が作業役の言う状態（完了・質問あり・止まっている・続ける）と事実です。",
            "   知らせの状態が「不明」（状態の行がない）でも、`agent team list` が作業中なら途中の区切りです：待ちます（log は開きません）。"
            "list の様子が変わらず待機中・止まっているときだけ、send で「返答の最後に状態の行を書いて、続けてください」と頼み、"
            "それでも動かなければ restart します。",
            "   知らせを読んだら、次のどれかを選びます：**取り込む**（`task diff`→`task finish`）・**直しを頼む**（send）・"
            f"**起動し直す**（restart）・**閉じる**（close）・**{up}に聞く**（send lead）。"
            "「注意なし」で状態が完了なら、差分を見て取り込んでかまいません。**注意があるものは、取り込む前に必ず報告・差分の中を"
            f"見て**、直しを頼むか{up}に聞きます（--no-check の提出を取り込むかは、{up}経由でユーザーに決めてもらいます）。",
            f"5. 結果は作業役の作業空間 `{TEAM_AREA}/<番号>-<名前>/` から読みます（報告は `{REPORT_FILE}`）。"
            f"`{program} agent team list` で一覧・報告の有無と、作業役の様子（作業中・待機中・止まっている、その長さ、"
            f"今していること、最後の返答）が分かります。何をしてきたかの詳しい流れは `{program} agent team log <名前>` で読めます。",
            "   知らせが長く来ないときは様子を見ます。止まっている・同じ作業中が長すぎる・最後の返答で迷っている作業役は、"
            f"send で伝えるか、`{program} agent team restart <名前>` で起動し直します（作業空間・作業はそのまま。既定は新しい会話で、"
            "どこまで進んだかを確かめてから続けます。`--resume` で前の会話の続きから）。",
            "   チームの操作（start・close・restart 等）が「止まっていました」「係が止まりました」で失敗したら、"
            f"`{program} agent team list` で途中までできたものを確かめ、同じことを繰り返さずに{up}に伝えます。",
            f"6. 取り込むときは、作業役の提出（このタスクブランチへの PR）を `{program} task diff <番号>` 等で確かめ、"
            f"`{program} task finish <番号>` で取り込みます（直してほしければ send で伝え、作業役がもう一度提出します）。"
            f"取り込んだら `{program} sync` で手元を最新にし、`{program} agent team close <名前>` で作業役の作業空間を閉じます"
            f"（取り込み済みを全員なら `close --merged`。作業中・届いていない言付けがあれば止まります。報告・任された仕事は "
            f"`{ARCHIVE}/` に写ります）。",
            "   手順は必ず守ります：`team start`→知らせを待つ→`task diff`→`task finish`→`sync`→`team close`。飛ばしません。"
            f"差分を確かめた後の finish・sync・close は `{program} agent team accept <名前>` で一度にできます"
            "（閉じられないときは何もしません）。",
            f"7. 作業役に追加で伝えたいことは `{program} agent team send <名前> <文>` で送れます（作業中でも、作業役の返答を"
            "止めずに次の区切りで届きます）。結果の番号で、届いたか（`agent team list --json` の messages）が分かり、まだ届いて"
            "いなければ `--cancel <番号>`・`--replace <番号>` で取り消し・置き換えができます。",
            "8. 作業役から「分けたい」と提案されたら、作業役を足します。受け持った仕事の中に、それだけで何人もの作業役に分けて"
            f"進める大きな部分があれば、**下に管理役を作って任せます**：`{program} agent team start <名前> --manager --brief <任せる部分>`"
            "（--brief の書き方は作業役と同じ）。下の管理役はその部分を計画して作業役に任せ、取り込んだら自分のタスクブランチを"
            "あなたのタスクブランチへ提出します。下の管理役の返答の終わり・要約・質問はあなたに届きます（その下の作業役の知らせは"
            "届きません）。取り込み・片付けは作業役と同じ手順です。小さな部分は下の管理役にせず、作業役に任せます。",
            f"   片付けてよいのは、自分の作業空間の中のタスクブランチ（`{program} task prune`・`task drop`）と、自分が作った作業役・管理役"
            f"（`{program} agent team close`）だけです。ほかの管理役・進行役のタスクブランチ・作業空間、GitHub にだけ残ったブランチには"
            "触りません（気づいたら進行役に伝えるだけ）。",
            "9. 作業役のモデルは既定でこのPCの設定（agent_worker_model）です。難しい仕事だけ `--model opus` 等で変えられます。",
            "10. ユーザーが作業役と直接話したいときは、ユーザーが引き取れます（`agent team takeover <名前>` で同じ会話を人の"
            "画面で開き、終わったら `agent team handback <名前>` で係に戻す）。引き取り・返しはユーザーがする操作です。",
            "",
            "### 手（当てはまるものを使う）",
            "- **レビューを任せる**（提出が多く、自分で全部を読むのが重いとき）：提出（PR の番号と作業役の名前）を読んで"
            "指摘を返す作業役を作ります。--brief に「提出を読んで指摘を報告に書く。コードは変えない。**提出しない**」と書きます。"
            "指摘を読んで、取り込むか、元の作業役に send で直しを頼むかを決めます。評価と直しの往復は多くても2回です。",
            "- **調べもの・アイデア出しを任せる**：調べることや、大量の案がほしいことを、何人かに分けて（観点を変えて）任せ、"
            "--brief に「結果は報告に書く。**提出しない**」と書きます。全員の報告を読んで選りすぐり、選んだものを実装の作業役に任せます。",
            f"- **提出しない作業役の片付け**（調べもの・レビュー。`--report-only` で作る）：作業役は報告を書くと "
            f"`{program} agent report` で知らせます。報告を読んだら `{program} task close <番号>` で子タスクを閉じ、"
            f"`{program} agent team close <名前>` で作業空間を閉じます（報告は `{ARCHIVE}/<番号>-<名前>/` に残ります。"
            f"ほかの人にも残すものは `{program} task comment` で Issue に書きます）。",
            "",
        ]
        ninth = next(i for i, line in enumerate(lines) if line.startswith("10. "))
        lines[ninth + 1:ninth + 1] = [
            f"11. {up}へは `{program} agent team send lead <文>` で送ります：ユーザーに聞きたいこと（質問あり）、区切りの要約"
            f"（何を取り込んだか・残り・気になること）。ECOBuild の手順を外れる判断は、{up}経由でユーザーに決めてもらいます。",
            f"12. 返答の最後には1行、`状態：{'／'.join(STATES)}` のどれかを書きます（ECOBuild が{up}へ知らせます。"
            f"受け持った部分を取り込みまで終えたら完了、{up}の答えが要るなら質問あり）。",
            f"13. 受け持った仕事を全部取り込んだら、自分のタスクブランチを `{program} task submit` で提出し、{up}に send で"
            f"要約を伝えます（提出を取り込むのは{up}です）。"]
    else:
        lines = [
            "## あなたの役：作業役",
            "",
            "あなたは作業役です。任された1つの仕事を、この作業空間（自分の子タスクのタスクブランチ）で行います。",
            "",
        ]
        if info:
            up = ROLE_NAMES.get(info.get("lead_role"), ROLE_NAMES[MANAGER])   # 作った上の役（いまは管理役）
            only = bool(info.get("report_only")) or NO_SUBMIT in _brief_text(root)
            finish = (
                [f"- **この仕事は報告だけです（{NO_SUBMIT}）。** ファイルを変えず・コミットせず・提出しません。終わったら "
                 f"`{REPORT_FILE}` に報告を書き、`{program} agent report` で{up}に知らせて返答を終えます（子タスクは{up}が閉じます）。"]
                if only else
                [f"- 終わったら `{REPORT_FILE}` に報告（したこと・確かめたこと・残ったこと・気になったこと）を書き、"
                 f"`{program} task submit` で提出します（{up}のタスクブランチへの PR になります）。"
                 "任された仕事に「提出しない」とあるとき（レビュー・調べもの・アイデア出し等）は、ファイルを変えず・コミットせず、"
                 f"報告を書いて `{program} agent report` で知らせ、返答を終えます（子タスクは{up}が閉じます）。"])
            lines += [
                f"- 任された仕事は `{BRIEF_FILE}` にあります（子タスク #{info.get('task')} の本文と同じ）。範囲の外のことはしません。",
                *finish,
                f"- 区切りごと（調べ終えた・直し終えた・テストを通した 等）に、`{PROGRESS_FILE}` へ途中経過（したこと・分かったこと・"
                "次にすること）を数行ずつ書き足します。止まって起動し直されたとき、新しい会話はここから続けます。",
                f"- タスクと作業空間は{up}が用意しました。下の「ECOBuild の使い方」の作業の流れのうち、`{program} task new`・"
                f"`task start`・`task finish`・`workspace close` は使いません（取り込み・片付けは{up}がします）。",
                f"- 迷ったこと・決められないことは、勝手に決めずに報告に書いて返答を終えます（{up}が読みます）。",
                f"- ファイルの内容は Edit・Write の道具で直します（python の heredoc・`cat >>`・`sed -i` では書き換えません）。"
                f"追加・移動・削除は `{program} file add／move／remove` です。",
                f"- **ビルド・テスト・提出の結果を待つために、返答を終えません。** `{program} test`・`build`・`check`・`task submit` は"
                "前面で動かし、終わるまでその返答の中で待って、結果を読んでから続けます。裏で動かしたときは、終わるまで自分で出力を"
                "確かめ続けます。「結果を待っています」と書いて返答を終えると、あなたは自分では起きられず、止まったままになります。",
                f"- 返答を終えてよいのは、(a) 提出まで終えた〔提出しない仕事なら報告まで〕、(b) {up}の答えが要る、(c) 自分では進められない、"
                "のときだけです。",
                "- 動かせなかった確認（道具がない〔node がなく JS のテストが動かない 等〕・環境の問題）は、報告に書き、状態を「質問あり」に"
                "します。黙って提出へ進みません。",
                f"- 見えるのは、この作業空間と GitHub だけです（{up}の作業空間は見えません）。{up}から渡されたパスが見えないときは、"
                "勝手に探さず、報告に書いて質問します。",
                "- 報告は結論を先頭に（完了／質問／止まった理由を2〜3行）、確かめたことはコマンドと結果で、推測は「推測」と書きます。"
                "長いログは貼らず、場所を書きます。",
                f"- **作業役・管理役を自分では作りません**（`{program} agent team start`・`agent team list` は使えません）。"
                f"分けた方がよいと思ったら、分け方の提案を報告に書いて{up}に伝えます。調べもの・確認など、この作業空間の中だけの"
                "小さな手伝いには、Claude Code のサブエージェントを使って構いません。",
                f"- **（最後の規則）返答を終えるたびに、途中の区切りでも、最後の1行は `状態：{'／'.join(STATES)}` のどれかです。"
                f"書かないと{up}に「不明」と知らされ、様子を調べに来られます。**（完了：提出まで終えた〔提出しない仕事なら報告まで〕。"
                f"質問あり：{up}の答えが要る。止まっている：自分では進められない。続ける：まだ途中。ECOBuild はこの行と、"
                f"作業空間・提出の様子を照らして{up}に知らせます。）",
                "",
            ]
    return lines


def _brief_text(root: Path) -> str:
    try:
        return (Path(root) / BRIEF_FILE).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""


def _lead_briefing(program: str) -> list[str]:
    """進行役の決まり：ユーザーとのやりとりに特化し、話の流れに応じて仕事ごとに管理役を作り、命令（send）で進める。"""
    return [
        "## あなたの役：進行役",
        "",
        "あなたは進行役です。**ユーザーとのやりとりに特化**します：話を聞いて何をするかを決め、話の流れに応じて**仕事ごとに"
        "管理役を作り**（何人でも）、決めた内容をその仕事の管理役へ命令し、管理役たちからの要約をユーザーに伝えます。"
        "**作業役は直接作りません**（作るのは管理役です）。"
        f"**書けるのは `{PLAN_FILE.rsplit('/', 1)[0]}/` の中（計画・命令の下書き）だけです**（編集・書き込みの道具はそこだけ使えます）。"
        "Bash（python・sed・リダイレクト等）でファイルを書く抜け道は使いません。",
        "**ECOBuild の手順を外れることは、ユーザーの了承なしに決めない・指示しない**：確認を省く（`--no-check`）、"
        "ビルド・テストを ECOBuild のコマンドの代わりに直接動かす、等。手順どおりに進められないときは、管理役を止めて待たせ、"
        "ユーザーに伝えて決めてもらいます。",
        "",
        "### 進め方",
        f"1. まず {PLAN_FILE} に、ユーザーと決めたこと（仕事ごとに：目的・範囲・順番・守ること・受け持つ管理役の名前）を書き、"
        "話が進むたびに更新します。",
        f"2. 仕事の話が決まったら、その仕事の管理役を作ります：`{program} agent team start <名前> --manager --brief <最初の命令>`"
        "（仕事ごとにタスクと作業空間ができ、係が画面なしで動かし始めます）。<名前> は仕事が分かる短い名前です（タスクブランチの"
        "名前にもなります）。--brief には**目的**・**返してほしいもの**（要約に書くこと）・**範囲**（やらないこと）を書きます。",
        "3. **会話の途中で別の仕事の話が始まったら、別の管理役を作ります**（今の管理役に混ぜません。1人の管理役は1つの仕事＝"
        "1つのタスクです）。今の仕事の続き・直し・追加なら、新しく作らずにその仕事の管理役へ送ります。どちらか迷ったら、"
        "「別のタスクとして取り込めるか」で決めます（決めた分け方は、ユーザーに一言伝えます）。同じファイルに触る仕事どうしは、"
        "範囲（触らないもの）を --brief に書き分けます。",
        f"4. 命令は `{program} agent team send <管理役の名前> <文>` で送ります（作業中でも、返答を止めずに次の区切りで届きます）。"
        "ユーザーと決まったことを、そのたびに、その仕事の管理役へまとめて送ります。作業役を作る・待つ・差分を確かめる・"
        "取り込む（task finish）・閉じる、はすべて管理役の仕事です。自分では作業役に触れません。",
        "5. 管理役の返答が終わると、ECOBuild がこの会話に知らせます（どの管理役か、1行目は ECOBuild が調べた注意、次が管理役の言う"
        "状態〔完了・質問あり・止まっている・続ける〕と事実）。管理役が `send` で返す要約とあわせて、**ユーザーに分かる言葉で、"
        "どの仕事の話かが分かるように要約して伝えます**。管理役の質問は、ユーザーに聞いて、答えをその管理役へ send します。"
        "作業役・下の管理役の返答の知らせは、あなたには届きません（管理役に届きます）。",
        "6. 管理役は、仕事を全部取り込むと、自分のタスクブランチを提出して知らせます。提出の取り込みは、ユーザーに確かめてから"
        f"（`{program} task finish <番号>`）、その管理役を `{program} agent team close <名前>` で閉じます。"
        "やめた仕事の管理役も、ユーザーに確かめてから閉じます。",
        f"7. 様子は `{program} agent team list --nested`（管理役たちと、その作業役・下の管理役）で見られます。管理役が止まったときは"
        f"`{program} agent team restart <名前>` で起動し直します（`--resume` で前の会話の続きから）。",
        "8. 管理役のモデルは既定でこのPCの設定（agent_manager_model）です。",
        "9. ユーザーが作業役と直接話したいときは、ユーザーが引き取れます（`agent team takeover <名前>`・`handback`）。"
        "引き取り・返しはユーザーがする操作です。",
        "",
    ]


def module_lead_briefing(program: str) -> list[str]:
    """モジュールの進行役（タスクを持たない専用の作業空間）に足す決まり：モジュールの管理（GitHub 側）もする。"""
    return [
        "### モジュールの進行役として",
        "- ここはモジュールの進行役の作業空間（ECOBuild が用意した、作成元のブランチの clone）で、タスクブランチではありません。"
        "**リポジトリのファイルは変えません**（コミット・push もしません）。管理役を作ると、親のない新しいタスクと、"
        "そのタスクブランチの作業空間ができます。",
        f"- 見る：`{program} status`・`task list`・`task status <番号>`・`branch list`・`ci status`・`module show` 等は自由に使えます。"
        "コードは読むだけ（ls・cat・grep・git log・git diff）。",
        f"- GitHub 側の管理はあなたが直接できます：共有ブランチ（`{program} branch create/delete/merge/protect`）・タスク"
        "（`task new`・`task close`）・届いた提出の処理（`task approve`・`task reject`・`task finish <番号>`）・メンバー"
        "（`module members`）・CI の実行（`ci run`）。",
        "- **取り返しのつかない操作・ほかの人に届く操作**（消す・取り込む・承認・閉じる 等）は、実行する前に、実行するコマンドを"
        "そのまま示してユーザーに聞き、「はい」と答えてもらってから実行します（ECOBuild が確かめ、答えがなければ止めます）。",
        "- リポジトリのファイルを変える設定（`module settings` の値・`ci init`・Dockerfile 等）は、タスクブランチの仕事なので管理役に命令します。",
        "- 人がする操作（秘密の値・このPCの準備・更新）は、ユーザーに頼みます。",
        "- 下の「ECOBuild の使い方」の「合うコマンドがないときは直接して構いません」は、進行役には当てはまりません。"
        "git・gh は読むだけ使えます（変える操作は、ユーザーが「はい」と答えても通りません）。合う ECOBuild のコマンドがなければ、"
        "別の方法を探さずに、できないこと（ECOBuild に足りないコマンド）としてユーザーに伝えます。",
        f"- コマンドは、使う前に `{program} <コマンド> --help` で引数を確かめます（ない引数を付けない）。エージェントの様子は "
        f"`{program} agent status`・`agent team list --nested`・`agent team log <名前>` で読めます。",
        "- タスクブランチ・作業空間を消す片付けはしません（あなたの作業空間にはタスクブランチがなく、ほかはすべて自分の管理の外です）。"
        "管理役のものは管理役が、自分の作業空間の中のものだけを片付けます。ほかの管理役・ほかの進行役のタスクブランチ、"
        "そのタスクの作業空間、GitHub にだけ残ったブランチには触りません。残っているのに気づいたら、ユーザーに伝えるだけにします"
        "（`task drop`・`workspace close` はユーザーがします）。",
        "",
    ]


def inbox_of(root: Path) -> Path:
    """作業空間 root のエージェントの、状態の置き場所（受け箱がある）。"""
    return agent_status.directory(container.name(root))


def send(root: Path, name: str, text: str) -> Member:
    """進行役（作業空間 root）から、チームの1人（name）へ言付けを送る（相手の受け箱に入れる）。結果の message_id は
    言付けの番号（取り消し・置き換え。team list の messages）。"""
    if not text.strip():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "伝えることが空です。")
    info = member_info(root)
    sender = info.get("name") or Path(root).name
    mine_team = team(root, owner_session()).members
    if name in UP_NAMES and info.get("lead") and not any(name in (m.name, m.path.name) for m in mine_team):
        up = Path(info["lead"])   # 上の役（作った進行役）へ：管理役の要約・質問。作った会話にだけ届ける
        file = agent_status.put(inbox_of(up), f"[{ROLE_NAMES.get(info.get('role'), '管理役')}「{sender}」から] {text}",
                                sender=str(Path(root)), owner=notice_owner(root))
        return Member(up.name, LEAD, up, 0, message_id=agent_status.item_id(file))
    member = find(root, name, owner_session())
    mine = ROLE_NAMES.get(info.get("role") or LEAD, "進行役")
    folder = inbox_of(member.path)
    file = agent_status.put(folder, f"[{mine}「{sender}」から] {text}", sender=str(Path(root)))
    key = agent_status.item_id(file)
    _log_sent(folder, {"id": key, "at": time.time(), "text": " ".join(text.split())[:80]})
    return Member(**{**member.__dict__, "message_id": key})


REPORT_KIND = "report"   # 受け箱のものの種類：作業役が agent report で出した報告の知らせ


def report(root: Path) -> dict:
    """作業役（作業空間 root）の報告（REPORT_FILE）を、作った上の役に知らせて「報告済み」にする（agent report）。
    このPCで動かす（コンテナの中からは係に頼む）。"""
    info = member_info(root)
    if not info.get("lead"):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "この作業空間はチームの1人ではありません（知らせる上の役がいません）。")
    file = Path(root) / REPORT_FILE
    try:
        text = file.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        text = ""
    if not text:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"報告（{REPORT_FILE}）がありません。",
                            hint="結論を先頭に報告を書いてから、もう一度 agent report してください。")
    lead = Path(info["lead"])
    try:
        place = Path(root).resolve().relative_to(lead.resolve()).as_posix()
    except ValueError:
        place = Path(root).as_posix()
    who = f"{ROLE_NAMES.get(info.get('role'), '作業役')}「{info.get('name') or Path(root).name}」"
    head = " ".join(text.split())[:400]
    put = agent_status.put(inbox_of(lead), f"[ECOBuild] {who}（子タスク #{info.get('task')}）が報告しました："
                                            f"{place}/{REPORT_FILE}（更新 {_clock(file.stat().st_mtime)}）。\n報告の頭：{head}",
                           sender=str(Path(root)), owner=notice_owner(root), kind=REPORT_KIND)
    folder = inbox_of(root)
    folder.mkdir(parents=True, exist_ok=True)
    told = {"at": time.time(), "id": agent_status.item_id(put), "mtime": file.stat().st_mtime}
    agent_status._write(folder / REPORTED, told)
    return {"name": info.get("name") or Path(root).name, "path": str(Path(root)), "lead": str(lead),
            "report": f"{place}/{REPORT_FILE}", **told}


SENT = "sent.jsonl"   # 作業役の状態の置き場所の中：送った言付け（番号・時刻・頭。取り消したもの）。届いたかは受け箱で見る
SENT_SHOWN = 20       # team list の messages に出す、新しいほうからの数


def _log_sent(folder: Path, entry: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / SENT, "a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def messages(folder: Path, limit: int = SENT_SHOWN) -> list[dict]:
    """作業役（状態の置き場所 folder）へ送った言付け：[{id, sent（時刻）, delivered（届いた）, cancelled, text}]。古い順。"""
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
    shown = list(found.values())[-limit:]
    for entry in shown:
        entry["delivered"] = not entry["cancelled"] and entry["id"] not in waiting
    return shown


def cancel(root: Path, name: str, key: str) -> Member:
    """まだ届いていない言付け key を取り消す（受け箱から出す）。届いた後なら止める。"""
    member = find(root, name, owner_session())
    folder = inbox_of(member.path)
    if not any(entry["id"] == key for entry in messages(folder, limit=10 ** 6)):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"「{member.name}」へ送った言付けに {key} はありません。",
                            hint="番号は send の結果・agent team list --json の messages で分かります。")
    if not agent_status.withdraw(folder, key):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"言付け {key} は、もう届いています（取り消せません）。",
                            hint="直したいことは、もう一度 send で伝えてください。")
    _log_sent(folder, {"id": key, "cancelled": time.time()})
    return Member(**{**member.__dict__, "message_id": key})


# 返答の終わり：係が事実をそろえて、進行役に知らせる -------------------------------------------------------
# 作業役の自己申告（状態の行・報告）だけに頼らず、係が作業空間と GitHub を直接調べ、食い違い・注意を先頭に書く
# （進行役は注意のないものを差分だけ見て取り込み、注意のあるものは中を見る：レビューの負荷を下げる）。
# 対話型の作業役（replied.json）でも、アプリ用の起動の結果でも同じものを使う（reply_facts・lead_notice）。

DONE, QUESTION, STUCK, GOING = "完了", "質問あり", "止まっている", "続ける"
STATES = (DONE, QUESTION, STUCK, GOING)   # 作業役が返答の最後の1行「状態：…」に書くもの
UNKNOWN_STATE = "不明"                    # 状態の行がない
_STATE_LINE = re.compile(rf"^[\s>*_`-]*状態[\s*_`]*[：:][\s*_`]*({'|'.join(STATES)})", re.MULTILINE)
NO_SUBMIT = "提出しない"                   # 任せる内容（brief）にこれがあれば、報告だけの仕事（レビュー・調べもの等）
AREA_HEADING, KEEP_OUT_HEADING = "持ち場", "触らない"   # 任せる内容（brief）の節：変えてよいパス・触らないパス
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*#*\s*$")
_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$")
_LISTED = 3                               # 注意に並べるファイルの数（ほかは「ほか n 件」）


@dataclass(frozen=True)
class ReplyFacts:
    """作業役の返答が終わったときに、係がその作業空間・GitHub を調べてそろえた事実（lead_notice の文のもと）。"""
    state: str                          # 作業役の言う状態（STATES。行がなければ UNKNOWN_STATE）
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
    changed: tuple[str, ...] = ()       # 進行役のタスクブランチから変えたファイル（未コミットのものも）
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
    """作業空間 root のエージェントの返答が終わったときの事実を調べる（時間のかかる check は動かさない）。
    調べられなかったものは unknown に書き、ほかは調べ続ける（知らせは必ず出す）。github：試験で差し替える。"""
    from ecobuild.module import submitted_check
    from ecowork import model as _work
    from ecowork.git import REMOTE
    from ecowork.repository import Repository
    root = Path(root)
    unknown = []
    try:
        brief = (root / BRIEF_FILE).read_text(encoding="utf-8")
    except (OSError, ValueError):
        brief = ""
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
            unknown.append(f"進行役のタスクブランチ {base} からの差分（{error}）")
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


REPORTED = "reported.json"   # 作業役の状態の置き場所の中：agent report で報告を知らせた時刻
FACTS = "facts.json"   # 作業役の状態の置き場所の中：最後の返答の終わりに係がそろえた事実（team list が GitHub に聞かずに読む）


def save_facts(root: Path, facts: ReplyFacts) -> None:
    """そろえた事実を作業役の状態の置き場所に残す（team list・close が読む）。"""
    from dataclasses import asdict
    folder = inbox_of(root)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        agent_status._write(folder / FACTS, {**asdict(facts), "at": time.time()})
    except OSError:
        pass


def saved_facts(root: Path) -> dict:
    """最後に残した事実（なければ空）。"""
    found = agent_status.read(inbox_of(root) / FACTS)
    return found if isinstance(found, dict) else {}


def member_details(root: Path) -> dict:
    """team list --json に足す、作業役（作業空間 root）の手元の記録（GitHub に聞かない・係を通さない）：
    submission（最後の返答の終わりに係が見た提出）・dirty（未コミットのファイル）・ahead（push していないコミット）・
    facts_at（それを調べた時刻）・messages（送った言付けと届いたか）・replies（返答を終えた回数）・
    report_at（報告を更新した時刻）・report_told（agent report で知らせた時刻）・report_read（その知らせが上の役に
    届いたか。知らせていなければ None）。"""
    folder = inbox_of(root)
    facts = saved_facts(root)
    pull = facts.get("pull")
    try:
        report_at = (Path(root) / REPORT_FILE).stat().st_mtime
    except OSError:
        report_at = None
    told = agent_status.read(folder / REPORTED)
    told = told if isinstance(told, dict) else None
    lead = member_info(root).get("lead")
    return {"submission": {"pull": pull, "state": facts.get("pull_state"), "checked": facts.get("checked"),
                           "head": facts.get("pull_head") or "", "at": facts.get("pulled_at")} if pull else None,
            "dirty": list(facts.get("uncommitted") or ()), "ahead": facts.get("unpushed") or 0, "facts_at": facts.get("at"),
            "messages": messages(folder), "replies": agent_status.replies(folder), "report_at": report_at,
            "report_told": told.get("at") if told else None,
            "report_read": None if told is None else bool(lead) and str(told.get("id") or "")
            not in agent_status.waiting_ids(inbox_of(Path(lead)))}


ARCHIVE = ".ecobuild/ai/team-archive"   # 進行役の作業空間の中：閉じた作業役の報告・任された仕事（<番号>-<名前>/）
KEPT = (REPORT_FILE, BRIEF_FILE, PROGRESS_FILE)   # 閉じる前に ARCHIVE へ写すもの


def close_problems(member: Member) -> list[str]:
    """作業役を閉じる前に止めるわけ（--force で閉じる）：作業中・届いていない言付け・提出の後のコミット。
    GitHub にないもの（未コミット・push していないコミット）は、閉じるときに作業空間の側で確かめる。"""
    from ecowork.git import Git
    found = []
    seen = agent_status.activity(inbox_of(member.path))
    if seen["state"] == agent_status.WORKING:
        found.append(f"「{member.name}」は作業中です")
    if seen.get("waiting"):
        found.append(f"「{member.name}」にまだ届いていない言付けが {seen['waiting']} 件あります")
    facts = saved_facts(member.path)
    if facts.get("pull") and facts.get("pull_head") and facts.get("pull_state") in ("open", "merged"):
        try:
            head = Git(member.path).output("rev-parse", "HEAD").strip()
        except Exception:
            head = ""
        if head and not head.startswith(facts["pull_head"]) and not facts["pull_head"].startswith(head):
            found.append(f"「{member.name}」には、提出（PR #{facts['pull']}）の後のコミットがあります")
    return found


def unpushed_files(member: Member) -> list[str]:
    """作業役の作業空間の、GitHub にないファイル（未コミットの変更・新しいファイル。close が断るときの details）。"""
    from ecowork.git import Git
    try:
        tree = Git(member.path).working_tree()
    except Exception:
        return []
    return list(dict.fromkeys(tree.staged + tree.unstaged + tree.conflicted + tree.untracked))


def archive(root: Path, member: Member) -> list[str]:
    """閉じる前に、作業役の報告・任された仕事・途中経過（KEPT）を進行役の ARCHIVE/<番号>-<名前>/ へ写す。写したもの。"""
    import shutil
    target = Path(root) / ARCHIVE / member.path.name
    kept = []
    for name in KEPT:
        source = member.path / name
        if source.is_file():
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target / Path(name).name)
            kept.append(f"{ARCHIVE}/{member.path.name}/{Path(name).name}")
    return kept


def forget_member(root: Path, member: Member) -> None:
    """閉じた作業役の受け箱と、進行役の受け箱のその作業役からのまだ届いていない知らせを消す。係が見回らないように、
    状態の置き場所の作業空間の記録も外す（出来事の記録は残す）。"""
    folder = inbox_of(member.path)
    if (folder / agent_status.INBOX).is_dir():
        remove_tree(folder / agent_status.INBOX)
    (folder / agent_status.WORKSPACE).unlink(missing_ok=True)
    agent_status.forget_from(inbox_of(Path(root)), str(member.path))


def merged_members(root: Path, owner: str | None = None) -> list[Member]:
    """提出（タスクブランチの PR）が取り込み済みの作業役（GitHub に聞く。close --merged）。"""
    from ecowork.repository import Repository
    found = []
    for member in team(root, owner).members:
        if not member.branch:
            continue
        pulls = Repository(member.path).github.pull_requests_for_branch(member.path, member.branch)
        if pulls and max(pulls, key=lambda p: p.number).state == "merged":
            found.append(member)
    return found


def _files(paths: tuple[str, ...]) -> str:
    shown = "、".join(paths[:_LISTED])
    return shown + (f" ほか {len(paths) - _LISTED} 件" if len(paths) > _LISTED else "")


def cautions(facts: ReplyFacts, role: str = WORKER) -> list[str]:
    """知らせの先頭に書く、食い違い・注意（なければ空：差分を見て取り込んでよい）。"""
    found = []
    submitted = facts.pull is not None and facts.pull_state != "closed"
    if facts.state == UNKNOWN_STATE and role in (WORKER, MANAGER):
        found.append("返答の最後に状態の行がありません（作業中なら途中の区切り：待つ。待機中で変化がなければ send で状態の行を頼む。"
                     "テスト待ちで返答を終えて止まった可能性もあります）")
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
        found.append("check を通した版の後のコミットが提出に入っています（task submit で出し直していません）")
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


def _facts_line(facts: ReplyFacts, report: str) -> str:
    """状態と事実の1行。"""
    if facts.pull is None:
        submission = "なし"
    else:
        kind = {"open": "下書き" if facts.draft else "開いている", "merged": "取り込み済み", "closed": "閉じた"}
        checked = {True: "・check を通した", False: "・--no-check", None: ""}[facts.checked]
        submission = f"PR #{facts.pull}（{kind.get(facts.pull_state, facts.pull_state)}{checked}）"
    changed = f"変えたファイル {len(facts.changed)}" + ("" if facts.scoped or not facts.changed else "（持ち場は照らしていません）")
    return f"状態：{facts.state}。{report}提出：{submission}。{changed}。"


def notice_owner(root: Path) -> str:
    """作業役（作業空間 root）の知らせを受け取る会話（作った会話の ID。分からなければ空＝どの会話にも）。"""
    return str(member_info(root).get("owner") or "")


def _clock(at: float) -> str:
    return time.strftime("%m/%d %H:%M", time.localtime(at))


def _report_line(root: Path, place: str, reported: bool, last_sent: float | None) -> str:
    """報告の1行：場所と、更新した時刻・最後の言付けより前か後か（前なら古い報告かもしれない）。"""
    if not reported:
        return f"報告：まだありません（{place}/{REPORT_FILE}）。"
    try:
        changed = (Path(root) / REPORT_FILE).stat().st_mtime
    except OSError:
        return f"報告：{place}/{REPORT_FILE}。"
    when = f"更新 {_clock(changed)}"
    if last_sent is not None:
        when += "、最後の言付けより後" if changed >= last_sent else "、最後の言付けより前（言付けの後は書き直していません）"
    return f"報告：{place}/{REPORT_FILE}（{when}）。"


def _submission_line(facts: ReplyFacts, last_sent: float | None) -> str:
    """提出が最後の言付けより前か後か（前なら、言付けの後に出し直していない）。"""
    if facts.pull is None or facts.pulled_at is None or last_sent is None or facts.pull_state == "closed":
        return ""
    return "提出は最後の言付けより後の版です。" if facts.pulled_at >= last_sent else "提出は最後の言付けより前の版です（出し直していません）。"


def lead_notice(root: Path, message: str, *, facts: ReplyFacts | None = None, continued: int = 0,
                merged: int = 0) -> tuple[Path, str] | None:
    """作業役（作業空間 root）の返答が終わったときに、作った進行役へ送る知らせ：(進行役の作業空間, 文)。
    先頭に注意（なければ「注意なし」）、次に状態と事実（子タスク・何回目の返答・報告と提出が最後の言付けより前か後か・
    届いていない言付け）、最後に最後の返答の頭。チームの1人でなければ None。
    facts：そろえた事実（省けば reply_facts で調べる。調べたものは save_facts で残す）。continued：受け箱の言付けを
    受け取って続けている（返答を終えていない：事実は調べず、短く知らせる）。merged：この知らせにまとめた、まだ届いて
    いなかった前の知らせの数。"""
    info = member_info(root)
    if not info.get("lead"):
        return None
    lead = Path(info["lead"])
    try:
        place = Path(root).resolve().relative_to(lead.resolve()).as_posix()
    except ValueError:
        place = Path(root).as_posix()
    who = f"{ROLE_NAMES.get(info.get('role'), '作業役')}「{info.get('name') or Path(root).name}」"
    folder = inbox_of(root)
    count = agent_status.replies(folder)
    head = f"子タスク #{info.get('task')}" + (f"・返答 {count} 回目" if count else "")
    if continued:
        return lead, f"[ECOBuild] {who}（{head}）は、言付け {continued} 件を受け取って続けています（返答はまだ終わっていません）。"
    if facts is None:
        facts = reply_facts(root, message)
        save_facts(root, facts)
    sent = [entry["sent"] for entry in messages(folder) if not entry["cancelled"] and isinstance(entry.get("sent"), (int, float))]
    last_sent = max(sent) if sent else None
    found = cautions(facts, str(info.get("role") or WORKER))
    caution = "注意：" + "／".join(found) if found else "注意なし"
    waiting = agent_status.activity(folder).get("waiting") or 0
    extra = _submission_line(facts, last_sent) + (f"届いていない言付け {waiting} 件。" if waiting else "") \
        + (f"（まだ読まれていない前の知らせ {merged} 件を、これにまとめました）" if merged else "")
    last = " ".join((message or "").split())[:400]
    return lead, (f"[ECOBuild] {who}（{head}）の返答が終わりました。{caution}\n"
                  f"{_facts_line(facts, _report_line(root, place, facts.reported, last_sent))}{extra}"
                  + (f"\n最後の返答：{last}" if last else ""))


# 頼み（コンテナの中・GUI の端末の進行役から、このPCの係へ） -------------------------------------------------

def should_forward() -> bool:
    """この操作を係に頼むか：コンテナの中（このPCに届かない）か、GUI のエージェントの窓の端末の中（係に起動してもらう）。"""
    return bool(os.environ.get(container.INSIDE) or os.environ.get(WINDOW_VARIABLE))


def requests_folder(root: Path) -> Path:
    """頼みの置き場所：状態の置き場所の中（コンテナの中ではマウントした所）。"""
    if os.environ.get(container.INSIDE):
        return Path(agent_status.INSIDE) / REQUESTS
    return agent_status.directory(container.name(root)) / REQUESTS


def forward(root: Path, args: list[str], cwd: Path, *, timeout: float = REQUEST_TIMEOUT,
            wait=time.sleep, progress=lambda message: None) -> dict:
    """このPCの係（agent_serve）に ecobuild のコマンド（args。cwd：root の中の場所）を実行してもらい、その JSON の結果
    （{ok, result|error}）を返す。係が動いていなければ（拾われなければ）止める。待つ間、係の途中経過を progress に渡し、
    途中経過が途切れたら（係が止まった）止める。"""
    folder = requests_folder(root)
    folder.mkdir(parents=True, exist_ok=True)
    beat = agent_status.read(folder / SERVE_BEAT)   # 係が動いているか、先に見る（止まっていれば待たない）
    if isinstance(beat, dict) and isinstance(beat.get("at"), (int, float)) and time.time() - beat["at"] > BEAT_STALE:
        raise EcoBuildError(ErrorCode.AGENT_ERROR,
                            f"ECOBuild の係（agent serve）が止まっています（最後に動いていたのは {int(time.time() - beat['at'])} 秒前）。",
                            hint="このPCで GUI を起動し直すか、ecobuild agent serve を起動してから、やり直してください"
                                 "（agent team list は係なしでも読めます。様子は分かりません）。")
    key = uuid.uuid4().hex
    try:
        relative = Path(cwd).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        relative = "."
    request = folder / f"{key}.json"
    temporary = folder / f"{key}.tmp"
    temporary.write_text(json.dumps({"id": key, "args": args, "cwd": relative, "at": time.time()}, ensure_ascii=False),
                         encoding="utf-8")
    os.replace(temporary, request)
    result = folder / f"{key}.result.json"
    report = folder / f"{key}{PROGRESS}"
    started, told, picked = time.monotonic(), None, None
    while time.monotonic() - started < timeout:
        seen = agent_status.read(report)
        if picked is None and not request.exists():
            picked = time.monotonic()
        if seen is None and picked is not None and not result.is_file() \
                and time.monotonic() - picked > SERVE_SILENT:   # 拾ったのに途中経過を書かない：係が消えた・古い係
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "ECOBuild の係（agent serve）が、頼みを受け取ったまま応えません。",
                                hint="GUI が閉じたか、係が古い ECOBuild のままです。GUI を起動し直してから、agent team list で"
                                     "途中までできたものを確かめ、やり直してください。")
        if isinstance(seen, dict) and not result.is_file():
            if seen.get("doing") and seen["doing"] != told:
                told = seen["doing"]
                progress(f"係：{told}")
            if isinstance(seen.get("at"), (int, float)) and time.time() - seen["at"] > SERVE_SILENT:
                raise EcoBuildError(ErrorCode.AGENT_ERROR, "ECOBuild の係（agent serve）が、頼みの途中で止まりました。",
                                    hint="GUI が閉じたか、係が終わったようです。GUI を起動し直してから、agent team list で"
                                         "途中までできたものを確かめ、やり直してください。")
        if result.is_file():
            try:
                doc = json.loads(result.read_text(encoding="utf-8"))
            except ValueError:   # 書いている途中
                wait(0.5)
                continue
            result.unlink(missing_ok=True)
            return doc
        if request.exists() and time.monotonic() - started > 15:   # 15秒たっても拾われない：GUI がない
            request.unlink(missing_ok=True)
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "ECOBuild の係（agent serve）が頼みを受け取りませんでした。",
                                hint="このPCで ecobuild agent serve が動いているか確かめてください（GUI は自分で起動します）。")
        wait(0.5)
    raise EcoBuildError(ErrorCode.AGENT_ERROR, "係の結果を待ちきれませんでした。", hint="GUI の窓・係の様子を確かめてください。")
