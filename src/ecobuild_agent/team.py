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
作業役のタブを開いてもらうため同じ道を使う（WINDOW_VARIABLE）。

言付け（send）と、作業役の返答が終わった知らせ（lead_notice）は、相手のエージェントの受け箱（agent_status.put）に入れる。
届けるのはエージェントを動かしている側（GUI の窓等）。

進行役はチームの様子（作業中・待機中・止まっている。team）を見て、止まった・迷った作業役を起動し直せる（restart_plan。
作業空間・ブランチ・作業はそのまま。新しい会話か、続きから）。頼みの途中経過は係が書き（PROGRESS）、頼んだ側は
それを見ながら待つ（係が止まれば、すぐに分かる）。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import ecobuild_container as container
from ecobuild import settings as _settings
from ecobuild.errors import EcoBuildError

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
LEAD_DENIED_TOOLS = ("Edit", "Write", "NotebookEdit")   # 進行役には使わせない（作業は作業役に任せる）
REQUESTS = "requests"               # 状態の置き場所の中の、頼みの置き場所
WINDOW_VARIABLE = "ECOBUILD_AGENT_WINDOW"   # GUI のエージェントの窓の端末で 1（頼みを係に渡す）
REQUEST_TIMEOUT = 1800              # 頼みの結果を待つ秒数（clone・イメージ作り込みで長くかかることがある）
STALL_SECONDS = 120                 # 頼みを実行する ecobuild が、この秒数なにも経過を出さなければ止まったとみなす（係が止める）
PROGRESS = ".progress.json"         # 頼みの置き場所の中：<id>.progress.json（係が書く途中経過。係が動いている間は毎秒）
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
    """Claude Code に足す引数：モデル（記録、なければこのPCの役の設定。指定済みなら足さない）と、進行役の使わせない道具。"""
    if command[:1] != ("claude",):
        return command
    model = member_info(root).get("model") or model_for(role)
    extra = []
    if model and "--model" not in command:
        extra += ["--model", model]
    if role == LEAD and "--disallowedTools" not in command:
        extra += ["--disallowedTools", ",".join(LEAD_DENIED_TOOLS)]
    return (*command, *extra)


def create(module, name: str, brief: str, *, role: str = WORKER, model: str = "",
           progress=lambda message: None) -> Member:
    """進行役の作業空間 module に、チームの1人を作る：子タスク（題名 name・本文 brief）と、そのタスクブランチを置いた
    作業空間（TEAM_AREA/<番号>-<名前>）。任された仕事・記録を作業空間の .ecobuild/ai に置く。起動はしない。"""
    from ecobuild import workspaces as _workspaces
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
    progress(f"子タスク「{name}」を作っています…")
    task = module.repository.create_task(name, body=brief, parent=lead_task.number)
    directory = module.root / TEAM_AREA / f"{task.number}-{label}"
    progress(f"子タスク #{task.number} の作業空間を用意しています（clone・依存先）…")
    member_module = module.start_task_in(task.number, directory, name=label)
    progress("作業空間ができました。任せる仕事を置いています…")
    _workspaces.record_quietly(member_module.root)
    _inherit_container(module.root, member_module.root)
    member_module.prepare_agent_area()
    (member_module.root / BRIEF_FILE).write_text(brief.rstrip() + "\n", encoding="utf-8", newline="\n")
    info = {"role": role, "name": name, "task": task.number, "lead": str(module.root), "model": model.strip()}
    (member_module.root / MEMBER_FILE).write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    branch = member_module.repository.git.current_branch() or ""
    return Member(name, role, member_module.root, task.number, branch, model.strip(), str(module.root),
                  prompt=FIRST_PROMPT[role])


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
                            last_reply=seen["last_reply"], context=seen["context"], waiting=seen["waiting"]))
    return Team(Path(root), tuple(found))


def restart_plan(root: Path, name: str, *, resume: bool = False) -> Member:
    """チームの1人（name）を起動し直すときの起動のしかた（作業空間・ブランチ・作業はそのまま。止めるのは呼ぶ側）。
    resume：前の会話の続きから（Claude Code の --resume。会話が分からなければ止める）。そうでなければ新しい会話で、
    どこまで進んだかを確かめてから続けさせる。"""
    member = find(root, name)
    if not resume:
        return Member(**{**member.__dict__, "prompt": RESTART_PROMPT.get(member.role, RESTART_PROMPT[WORKER])})
    info = agent_status.read(inbox_of(member.path) / "status.json")
    session = info.get("session") if isinstance(info, dict) else None
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
            "**自分ではファイルを編集しません**（編集・書き込みの道具は使えません。コードを書く・直すのは作業役です）。",
            "",
            "### 進め方",
            f"1. まず {PLAN_FILE} に計画を書きます（目的・分け方・順番・誰に何を任せたか）。話が長くなっても、ここを見れば続けられるように更新し続けます。",
            f"2. 任せるときは `{program} agent team start <名前> --brief <任せる内容>` で作業役を作ります（子タスクと、その作業空間ができ、"
            "作業役が別のタブで動き始めます）。<名前> はタスクブランチの名前にもなる短い名前です。",
            "   --brief には必ず次を書きます：**目的**（何のためか）、**返してほしいもの**（報告に書くこと・提出の形）、"
            "**使ってよい道具・見る場所**、**範囲**（やらないこと・触らないファイル）。短い指示は取り違え・重複のもとです。",
            "3. 作業役の人数は仕事の大きさで決めます：小さなことは1人（または任せずにユーザーと話すだけ）、分けられるものだけ2〜3人。"
            "**同じファイルを2人に任せません**（持ち場を分ける）。依存し合う仕事は順に任せます。",
            "4. 任せたら**作業役を待ちます**（自分で作業を始めない）。作業役の返答が終わると、ECOBuild がこの会話に知らせます。",
            f"5. 結果は作業役の作業空間 `{TEAM_AREA}/<番号>-<名前>/` から読みます（報告は `{REPORT_FILE}`）。"
            f"`{program} agent team list` で一覧・報告の有無と、作業役の様子（作業中・待機中・止まっている、その長さ、"
            "最後の返答）が分かります。",
            "   知らせが長く来ないときは様子を見ます。止まっている・同じ作業中が長すぎる・最後の返答で迷っている作業役は、"
            f"send で伝えるか、`{program} agent team restart <名前>` で起動し直します（作業空間・作業はそのまま。既定は新しい会話で、"
            "どこまで進んだかを確かめてから続けます。`--resume` で前の会話の続きから）。",
            "   チームの操作（start・close・restart 等）が「止まっていました」「係が止まりました」で失敗したら、"
            f"`{program} agent team list` で途中までできたものを確かめ、同じことを繰り返さずにユーザーに伝えます。",
            f"6. 取り込むときは、作業役の提出（このタスクブランチへの PR）を `{program} task diff <番号>` 等で確かめ、"
            f"`{program} task finish <番号>` で取り込みます（直してほしければ send で伝え、作業役がもう一度提出します）。"
            f"取り込んだら `{program} sync` で手元を最新にし、`{program} agent team close <名前>` で作業役の作業空間を閉じます。",
            f"7. 作業役に追加で伝えたいことは `{program} agent team send <名前> <文>` で送れます。",
            "8. 作業役から「分けたい」と提案されたら、作業役を足すか、その部分を受け持つ進行役を "
            f"`{program} agent team start <名前> --lead --brief …` で作ります（新しい窓で動きます）。",
            "9. 作業役のモデルは既定でこのPCの設定（agent_worker_model）です。難しい仕事だけ `--model opus` 等で変えられます。",
            "",
        ]
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
                f"`{program} task submit` で提出します（進行役のタスクブランチへの PR になります）。",
                "- 迷ったこと・決められないことは、勝手に決めずに報告に書いて返答を終えます（進行役が読みます）。",
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


def lead_notice(root: Path, message: str) -> tuple[Path, str] | None:
    """作業役（作業空間 root）の返答が終わったときに、作った進行役へ送る知らせ：(進行役の作業空間, 文)。
    チームの1人でなければ None。"""
    info = member_info(root)
    if not info.get("lead"):
        return None
    lead = Path(info["lead"])
    try:
        place = Path(root).resolve().relative_to(lead.resolve()).as_posix()
    except ValueError:
        place = Path(root).as_posix()
    report = (f"報告：{place}/{REPORT_FILE}。" if (Path(root) / REPORT_FILE).is_file()
              else f"（報告 {place}/{REPORT_FILE} はまだありません）。")
    last = " ".join((message or "").split())[:400]
    return lead, (f"[ECOBuild] {ROLE_NAMES.get(info.get('role'), '作業役')}「{info.get('name') or Path(root).name}」の"
                  f"返答が終わりました。{report}" + (f"\n最後の返答：{last}" if last else ""))


# 頼み（コンテナの中・GUI の端末の進行役から、このPCの係へ） -------------------------------------------------

def should_forward() -> bool:
    """この操作を係に頼むか：コンテナの中（このPCに届かない）か、GUI のエージェントの窓の端末の中（タブを開いてもらう）。"""
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
    started, told = time.monotonic(), None
    while time.monotonic() - started < timeout:
        seen = agent_status.read(report)
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
