"""進行役と作業役（エージェントのチーム）。

Anthropic の orchestrator-workers（lead が仕事を分けて任せ、結果をまとめる）に沿わせる：
- 進行役（lead）：ユーザーと話し、計画し、作業役に任せ、結果を読んで取り込む。自分ではファイルを編集しない。
- 作業役（worker）：任された1つの仕事を、自分の子タスク＋作業空間で行い、報告を書いて提出する（今の作業空間の
  エージェントと同じ）。

作業役は進行役のタスクの子タスクで、作業空間は進行役の作業空間の中の TEAM_AREA/<番号>-<名前>/（.ecobuild/ai の下：
git の除外の中）。子タスクのタスクブランチは親（進行役）のタスクブランチから作り、提出は親のタスクブランチへの PR に
なる。進行役は自分の場所（コンテナなら /work）から作業役のファイル・報告をそのまま読める。

作業役は ECOBuild の作業役を作らない（分けたくなったら進行役に提案する）。進行役は進行役を作れる（その部分を受け持つ
進行役。孫タスクがその作業役になる）。

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

LEAD, WORKER = "lead", "worker"
ROLES = (LEAD, WORKER)
ROLE_NAMES = {LEAD: "進行役", WORKER: "作業役"}
TEAM_AREA = ".ecobuild/ai/team"     # 進行役の作業空間の中の、作業役（と下の進行役）の作業空間の置き場所
MEMBER_FILE = ".ecobuild/ai/member.json"   # 作業役の作業空間の中：役・名前・タスク・進行役の場所・モデル
BRIEF_FILE = ".ecobuild/ai/brief.md"       # 任された仕事（進行役の指示）
REPORT_FILE = ".ecobuild/ai/report.md"     # 作業役の報告
PLAN_FILE = ".ecobuild/ai/plan.md"         # 進行役の計画
MODEL_KEYS = {LEAD: "agent_lead_model", WORKER: "agent_worker_model"}   # このPCの設定：役ごとのモデル
REQUESTS = "requests"               # 状態の置き場所の中の、頼みの置き場所
WINDOW_VARIABLE = "ECOBUILD_AGENT_WINDOW"   # GUI のエージェントの窓の端末で 1（頼みを係に渡す）
REQUEST_TIMEOUT = 1800              # 頼みの結果を待つ秒数（clone・イメージ作り込みで長くかかることがある）
STALL_SECONDS = 120                 # 頼みを実行する ecobuild が、この秒数なにも経過を出さなければ止まったとみなす（係が止める）
PROGRESS = ".progress"              # 頼みの置き場所の中：<id>.progress（係が書く途中経過。係が動いている間は毎秒。
                                    # .json にしない：頼み〔<id>.json〕と取り違える）
SERVE_SILENT = 30                   # 途中経過がこの秒数書かれなければ、係が止まったとみなす
FIRST_PROMPT = {
    WORKER: f"{BRIEF_FILE} に任された仕事があります。読んで作業を始めてください。終わったら {REPORT_FILE} に報告を書き、提出してください。",
    LEAD: f"{BRIEF_FILE} に任された部分があります。読んで計画を立て、作業役に任せて進めてください。",
}
RESTART_PROMPT = {   # 起動し直した（新しい会話）ときの最初の発言
    WORKER: f"進行役があなたを起動し直しました（前の会話は引き継いでいません）。{BRIEF_FILE} の任された仕事を読み、{REPORT_FILE}・"
            "git の状態・コミットの履歴から、どこまで進んでいるかを確かめてから続けてください。",
    LEAD: f"上の進行役があなたを起動し直しました（前の会話は引き継いでいません）。{BRIEF_FILE}・{PLAN_FILE}・チームの様子"
          "（agent team list）から、どこまで進んでいるかを確かめてから続けてください。",
}
RESUME_PROMPT = "進行役があなたを起動し直しました（この会話の続きです）。止まっていたところから続けてください。"


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
    app: bool = False           # 係がアプリ用で起動した（team start・restart の結果）
    note: str = ""              # 起動できなかったわけ等


@dataclass(frozen=True)
class Team:
    lead: Path
    members: tuple[Member, ...]


def model_for(role: str) -> str:
    """このPCの設定の、役のモデル（空なら Claude Code の既定）。"""
    return _settings.load_config().get(MODEL_KEYS[role], "").strip()


def member_info(root: Path) -> dict:
    """作業空間 root が作業役・下の進行役なら、その記録（なければ空）。"""
    try:
        data = json.loads((Path(root) / MEMBER_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def role_of(root: Path, chosen: str = "") -> str:
    """作業空間 root のエージェントの役：指定（chosen）、なければ記録、なければ作業役（今までの作業空間のエージェント）。"""
    role = chosen or member_info(root).get("role") or WORKER
    if role not in ROLES:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"役 {role!r} はありません。", hint="lead（進行役）か worker（作業役）です。")
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


def create(module, name: str, brief: str, *, role: str = WORKER, model: str = "",
           progress=lambda message: None) -> Member:
    """進行役の作業空間 module に、チームの1人を作る：子タスク（題名 name・本文 brief）と、そのタスクブランチを置いた
    作業空間（TEAM_AREA/<番号>-<名前>）。任された仕事・記録を作業空間の .ecobuild/ai に置く。起動はしない。

    何人も並べて作れる（係が並べて実行する）。同じ名前を同時には作らない（後のものは止める）。前に作りかけて止まった
    もの（開いた子タスク・作業空間のフォルダー）が残っていれば、それを片付けて続きから作る（二重に作らない）。途中で
    失敗したら、作りかけを片付けて（作業空間を消し、この回に作った子タスクを閉じて）、何が残ったかを失敗に書く。"""
    from ecowork import model as _work
    if role not in ROLES:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"役 {role!r} はありません。", hint="lead（進行役）か worker（作業役）です。")
    if role_of(module.root) == WORKER and member_info(module.root):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "作業役は、作業役・進行役を作りません。",
                            hint=f"分けたいときは、{REPORT_FILE} に分け方の提案を書いて進行役に伝えてください（進行役が作ります）。")
    label = _work.check_branch_label(name)
    if not brief.strip():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "任せる仕事（--brief）が空です。",
                            hint="目的・返してほしいもの・使ってよい道具・範囲（やらないこと）を書いてください。")
    lead_task = module.require_task_branch(f"{ROLE_NAMES[role]}の作成")
    module.prepare_agent_area()   # 進行役の側の git に、作業空間の置き場所を見せない（除外）
    with _creating(module, name):
        task = _leftover(module, lead_task.number, name, progress)
        created = task is None
        if created:
            progress(f"子タスク「{name}」を作っています…")
            try:
                task = module.repository.create_task(name, body=brief, parent=lead_task.number)
            except Exception as error:   # 作った後の読み直し等で失敗したもの：子タスクはできている
                made = _open_child(module, lead_task.number, name)
                raise _failed(error, name, role, made and _close_child(module, made.number, name, error), made) from error
        directory = module.root / TEAM_AREA / f"{task.number}-{label}"
        try:
            return _prepare(module, task.number, directory, name, label, brief, role, model, progress)
        except Exception as error:
            left = _clean_up(module, task.number, directory, name, error, close=created)
            raise _failed(error, name, role, left, task, resumed=not created) from error


def _prepare(module, number: int, directory: Path, name: str, label: str, brief: str, role: str, model: str,
             progress) -> Member:
    """子タスク number の作業空間 directory を作り、任された仕事・記録を置く。"""
    from ecobuild import workspaces as _workspaces
    progress(f"子タスク #{number} の作業空間を用意しています（clone・依存先）…")
    member_module = module.start_task_in(number, directory, name=label)
    progress("作業空間ができました。任せる仕事を置いています…")
    _workspaces.record_quietly(member_module.root)
    _inherit_container(module.root, member_module.root)
    member_module.prepare_agent_area()
    (member_module.root / BRIEF_FILE).write_text(brief.rstrip() + "\n", encoding="utf-8", newline="\n")
    info = {"role": role, "name": name, "task": number, "lead": str(module.root), "model": model.strip()}
    # 記録（MEMBER_FILE）は最後に置く：あれば作り終えた作業空間（なければ作りかけ。_leftover）
    (member_module.root / MEMBER_FILE).write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    branch = member_module.repository.git.current_branch() or ""
    return Member(name, role, member_module.root, number, branch, model.strip(), str(module.root),
                  prompt=FIRST_PROMPT[role])


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


def _open_child(module, parent: int, name: str):
    """親タスク parent の、題名 name の開いた子タスク（いちばん新しいもの。なければ None）。"""
    children = [issue for issue in module.repository.github.sub_issues(module.root, parent)
                if issue.title == name and issue.state == "open"]
    return max(children, key=lambda issue: issue.number) if children else None


def _clean_up(module, number: int, directory: Path, name: str, error: Exception, *, close: bool) -> list[str]:
    """作りかけを片付ける：作業空間 directory を消し、close なら子タスク number（とこの回に置いたタスクブランチ）を
    閉じる。片付けられなかったもの（文）を返す。"""
    from ecowork import model as _work
    from ecowork.git import Git
    left = []
    if close and (directory / ".git").exists():
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


def _failed(error: Exception, name: str, role: str, left, task, *, resumed: bool = False) -> EcoBuildError:
    """作成の失敗を、何が残ったか・どうすればよいかを添えて伝える。left：片付けられなかったもの（task がなければ None）。"""
    hint = getattr(error, "hint", None)
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
                         hint=after + (f"\n{hint}" if hint else ""), details=getattr(error, "details", None))


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


def team(root: Path) -> Team:
    """進行役の作業空間 root のチーム（TEAM_AREA の下の作業空間）。"""
    from ecowork.git import Git
    found = []
    area = Path(root) / TEAM_AREA
    for folder in sorted(area.iterdir()) if area.is_dir() else ():
        info = member_info(folder)
        if not info:
            continue
        try:
            branch = Git(folder).current_branch() or ""
        except Exception:   # 壊れた clone 等。場所だけ出す
            branch = ""
        seen = agent_status.activity(inbox_of(folder))
        found.append(Member(str(info.get("name", folder.name)), str(info.get("role", WORKER)), folder,
                            int(info.get("task") or 0), branch, str(info.get("model") or ""), str(info.get("lead") or ""),
                            (folder / REPORT_FILE).is_file(), state=seen["state"], since=seen["since"],
                            last_reply=seen["last_reply"], context=seen["context"], waiting=seen["waiting"],
                            mode=seen.get("mode", ""), doing=seen.get("doing", ""), doing_at=seen.get("doing_at"),
                            usage=seen.get("usage"), limits=seen.get("limits")))
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


def find(root: Path, name: str) -> Member:
    """チームの1人を名前（か番号・フォルダー名）で探す。"""
    for member in team(root).members:
        if name in (member.name, str(member.task), member.path.name):
            return member
    raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"チームに「{name}」はいません。",
                        hint="ecobuild agent team list で一覧を見られます。")


def briefing(root: Path, role: str, program: str) -> list[str]:
    """起動のときにエージェントへ渡す、役ごとの決まり（Anthropic のマルチエージェントの教訓に沿う）。"""
    info = member_info(root)
    if role == LEAD:
        lines = [
            "## あなたの役：進行役",
            "",
            "あなたは進行役です。ユーザーと話して何をするかを決め、仕事を分けて作業役に任せ、結果を読んで取り込みます。"
            f"**書けるのは `{PLAN_FILE.rsplit('/', 1)[0]}/` の中（計画・任せる内容の下書き）だけです**（編集・書き込みの道具は"
            "そこだけ使えます）。コード・文書を書く・直すのは作業役です。Bash（python・sed・リダイレクト等）でファイルを書く"
            "抜け道は使いません。",
            "**ECOBuild の手順を外れることは、ユーザーの了承なしに決めない・指示しない**：確認を省く（`--no-check`）、"
            "ビルド・テストを ECOBuild のコマンドの代わりに直接動かす、等。環境の問題で手順どおりに進められないときは、"
            "作業役を止めて待たせ、ユーザーに伝えて決めてもらいます（答えを待たずに進めると決めない）。",
            "",
            "### 進め方",
            f"1. まず {PLAN_FILE} に計画を書きます（目的・分け方・順番・誰に何を任せたか）。話が長くなっても、ここを見れば続けられるように更新し続けます。",
            f"2. 任せるときは `{program} agent team start <名前> --brief <任せる内容>` で作業役を作ります（子タスクと、その作業空間ができ、"
            "作業役は ECOBuild の係が画面なしで動かし始めます。タブ・画面は開きません）。<名前> はタスクブランチの名前にもなる短い名前です。",
            "   --brief には必ず次を書きます：**目的**（何のためか）、**返してほしいもの**（報告に書くこと・提出の形）、"
            "**使ってよい道具・見る場所**、**範囲**（やらないこと・触らないファイル）。短い指示は取り違え・重複のもとです。",
            f"   変えてよいファイルは `## {AREA_HEADING}`、触らないファイルは `## {KEEP_OUT_HEADING}` の節に、1行に1つのパス"
            "（フォルダー・ファイル・`src/ui/*.py` のような glob）の箇条書きで書きます。ECOBuild がこれと作業役の変更を照らして、"
            "外のファイルを変えたら知らせます（この形でなければ照らしません）。",
            "   何人も作るときは、1人ずつ終わるのを待たずに並べて頼みます（ECOBuild の係が数人ずつ並べて作ります。1人に"
            "数十秒かかるので、ループで順に待つと全員そろうまで長くかかります）：Bash の run_in_background で1人ずつ "
            f"`{program} agent team start <名前> --brief-file <ファイル>` を出し、終わった知らせ（結果）を待ちます。"
            "同じ名前は2回頼みません。",
            "   作成が途中で失敗したときは、ECOBuild が作りかけ（作業空間・子タスク）を片付け、何が残ったかを失敗の文に書きます。"
            "その文に従ってもう一度 start します（残った作りかけがあれば、それを片付けて続きから作ります。二重にはなりません）。",
            "3. 作業役の人数は仕事の大きさと独立さで決めます：小さなことは1人（または任せずにユーザーと話すだけ）、"
            "互いに依存しない部分に分けられるだけ並べます（大勢でもよい。下の「進め方の手」）。"
            "**同じファイルを2人に任せません**（持ち場を分ける）。依存し合う仕事は順に任せます。",
            "4. 任せたら**作業役を待ちます**（自分で作業を始めない）。作業役の返答が終わると、ECOBuild がこの会話に知らせます。"
            "知らせの1行目は ECOBuild が作業空間・GitHub を調べた注意（完了と言うのに提出がない・--no-check で提出・"
            "持ち場の外の変更・未コミットの変更 等）、次の行が作業役の言う状態（完了・質問あり・止まっている・続ける）と事実です。",
            "   知らせを読んだら、次のどれかを選びます：**取り込む**（`task diff`→`task finish`）・**直しを頼む**（send）・"
            "**起動し直す**（restart）・**閉じる**（close）・**ユーザーに聞く**。"
            "「注意なし」で状態が完了なら、差分を見て取り込んでかまいません。**注意があるものは、取り込む前に必ず報告・差分の中を"
            "見て**、直しを頼むかユーザーに聞きます（--no-check の提出を取り込むかは、ユーザーに決めてもらいます）。",
            f"5. 結果は作業役の作業空間 `{TEAM_AREA}/<番号>-<名前>/` から読みます（報告は `{REPORT_FILE}`）。"
            f"`{program} agent team list` で一覧・報告の有無と、作業役の様子（作業中・待機中・止まっている、その長さ、"
            f"今していること、最後の返答）が分かります。何をしてきたかの詳しい流れは `{program} agent team log <名前>` で読めます。",
            "   知らせが長く来ないときは様子を見ます。止まっている・同じ作業中が長すぎる・最後の返答で迷っている作業役は、"
            f"send で伝えるか、`{program} agent team restart <名前>` で起動し直します（作業空間・作業はそのまま。既定は新しい会話で、"
            "どこまで進んだかを確かめてから続けます。`--resume` で前の会話の続きから）。",
            "   チームの操作（start・close・restart 等）が「止まっていました」「係が止まりました」で失敗したら、"
            f"`{program} agent team list` で途中までできたものを確かめ、同じことを繰り返さずにユーザーに伝えます。",
            f"6. 取り込むときは、作業役の提出（このタスクブランチへの PR）を `{program} task diff <番号>` 等で確かめ、"
            f"`{program} task finish <番号>` で取り込みます（直してほしければ send で伝え、作業役がもう一度提出します）。"
            f"取り込んだら `{program} sync` で手元を最新にし、`{program} agent team close <名前>` で作業役の作業空間を閉じます。",
            f"7. 作業役に追加で伝えたいことは `{program} agent team send <名前> <文>` で送れます（作業中でも、作業役の返答を"
            "止めずに次の区切りで届きます）。",
            "8. 作業役から「分けたい」と提案されたら、作業役を足すか、その部分を受け持つ進行役を "
            f"`{program} agent team start <名前> --lead --brief …` で作ります（これも係が画面なしで動かします）。",
            "9. 作業役のモデルは既定でこのPCの設定（agent_worker_model）です。難しい仕事だけ `--model opus` 等で変えられます。",
            "10. ユーザーが作業役と直接話したいときは、ユーザーが引き取れます（`agent team takeover <名前>` で同じ会話を人の"
            "画面で開き、終わったら `agent team handback <名前>` で係に戻す）。引き取り・返しはユーザーがする操作です。",
            "",
            "### 進め方の手（場面に合わせて選ぶ）",
            "- **大勢に並べて任せる**（独立した部分が多い大きな仕事）：任せる前に、全員に共通の決まり（部分どうしの接点・"
            "名前・形式・触ってよい場所）を決めて計画に書き、それぞれの --brief に入れます。持ち場は重ならないように分け、"
            "互いの結果を待たないと進めない仕事は大勢に並べません。",
            "- **レビューを任せる**（提出が多く、自分で全部を読むのが重いとき）：提出（PR の番号と作業役の名前）を読んで"
            "指摘を返す作業役を作ります。--brief に「提出を読んで指摘を報告に書く。コードは変えない。**提出しない**」と書きます。"
            "指摘を読んで、取り込むか、元の作業役に send で直しを頼むかを決めます。",
            "- **調べもの・アイデア出しを任せる**：調べることや、大量の案がほしいことを、何人かに分けて（観点を変えて）任せ、"
            "--brief に「結果は報告に書く。**提出しない**」と書きます。全員の報告を読んで選りすぐり、選んだものを実装の作業役に任せます。",
            f"  提出しない作業役は、報告を読んだら `{program} task close <番号>` で子タスクを閉じ、"
            f"`{program} agent team close <名前>` で作業空間を閉じます（報告は閉じると消えるので、要るものは計画に写します）。",
            f"- **話す役と割り振る役を分ける**（作業役が多い・ユーザーとの話が長い・ユーザーが次々に頼むとき）：自分の下に進行役を"
            f"1人作り（`{program} agent team start <名前> --lead --brief …`）、作業役を作って割り振り・取り込むのはその進行役に"
            "任せます。自分はユーザーとの話に集中し、決まったことをまとめて send で送り続けます（作業中でも届きます）。"
            "下の進行役からの知らせは、要約してユーザーに伝えます。",
            "",
        ]
        if info.get("lead"):   # 下の進行役：上の進行役への知らせにも状態を書く
            ninth = next(i for i, line in enumerate(lines) if line.startswith("9. "))
            lines[ninth + 1:ninth + 1] = [f"10. あなたには上の進行役がいます。返答の最後には1行、`状態：{'／'.join(STATES)}` のどれかを書きます"
                            "（受け持った部分を提出まで終えたら完了）。"]
    else:
        lines = [
            "## あなたの役：作業役",
            "",
            "あなたは作業役です。任された1つの仕事を、この作業空間（自分の子タスクのタスクブランチ）で行います。",
            "",
        ]
        if info:
            lines += [
                f"- 任された仕事は `{BRIEF_FILE}` にあります（子タスク #{info.get('task')} の本文と同じ）。範囲の外のことはしません。",
                f"- 終わったら `{REPORT_FILE}` に報告（したこと・確かめたこと・残ったこと・気になったこと）を書き、"
                f"`{program} task submit` で提出します（進行役のタスクブランチへの PR になります）。"
                "任された仕事に「提出しない」とあるとき（レビュー・調べもの・アイデア出し等）は、ファイルを変えず・コミットせず、"
                "報告を書いて返答を終えます（子タスクは進行役が閉じます）。",
                "- 迷ったこと・決められないことは、勝手に決めずに報告に書いて返答を終えます（進行役が読みます）。",
                f"- **返答の最後には必ず1行、`状態：{'／'.join(STATES)}` のどれかを書きます**（完了：提出まで終えた〔提出しない仕事なら報告まで〕。"
                "質問あり：進行役の答えが要る。止まっている：自分では進められない。続ける：まだ途中）。"
                "ECOBuild はこの行と、作業空間・提出の様子を照らして進行役に知らせます。",
                f"- **作業役・進行役を自分では作りません**（`{program} agent team start` は使えません）。分けた方がよいと思ったら、"
                "分け方の提案を報告に書いて進行役に伝えます。調べもの・確認など、この作業空間の中だけの小さな手伝いには、Claude Code の"
                "サブエージェントを使って構いません。",
                "",
            ]
    return lines


def inbox_of(root: Path) -> Path:
    """作業空間 root のエージェントの、状態の置き場所（受け箱がある）。"""
    return agent_status.directory(container.name(root))


def send(root: Path, name: str, text: str) -> Member:
    """進行役（作業空間 root）から、チームの1人（name）へ言付けを送る（相手の受け箱に入れる）。"""
    if not text.strip():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "伝えることが空です。")
    member = find(root, name)
    sender = member_info(root).get("name") or Path(root).name
    agent_status.put(inbox_of(member.path), f"[進行役「{sender}」から] {text}", sender=str(Path(root)))
    return member


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
        except Exception as error:
            unknown.append(f"提出（{getattr(error, 'message', error)}）")
    return ReplyFacts(**found, unknown=tuple(unknown))


def _files(paths: tuple[str, ...]) -> str:
    shown = "、".join(paths[:_LISTED])
    return shown + (f" ほか {len(paths) - _LISTED} 件" if len(paths) > _LISTED else "")


def cautions(facts: ReplyFacts, role: str = WORKER) -> list[str]:
    """知らせの先頭に書く、食い違い・注意（なければ空：差分を見て取り込んでよい）。"""
    found = []
    submitted = facts.pull is not None and facts.pull_state != "closed"
    if facts.state == UNKNOWN_STATE and role == WORKER:
        found.append("返答の最後に状態の行がありません")
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


def lead_notice(root: Path, message: str, *, facts: ReplyFacts | None = None) -> tuple[Path, str] | None:
    """作業役（作業空間 root）の返答が終わったときに、作った進行役へ送る知らせ：(進行役の作業空間, 文)。
    先頭に注意（なければ「注意なし」）、次に状態と事実、最後に最後の返答の頭。チームの1人でなければ None。
    facts：そろえた事実（省けば reply_facts で調べる）。"""
    info = member_info(root)
    if not info.get("lead"):
        return None
    lead = Path(info["lead"])
    try:
        place = Path(root).resolve().relative_to(lead.resolve()).as_posix()
    except ValueError:
        place = Path(root).as_posix()
    facts = facts or reply_facts(root, message)
    report = f"報告：{place}/{REPORT_FILE}。" if facts.reported else f"報告：まだありません（{place}/{REPORT_FILE}）。"
    found = cautions(facts, str(info.get("role") or WORKER))
    caution = "注意：" + "／".join(found) if found else "注意なし"
    last = " ".join((message or "").split())[:400]
    return lead, (f"[ECOBuild] {ROLE_NAMES.get(info.get('role'), '作業役')}「{info.get('name') or Path(root).name}」の"
                  f"返答が終わりました。{caution}\n{_facts_line(facts, report)}" + (f"\n最後の返答：{last}" if last else ""))


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
