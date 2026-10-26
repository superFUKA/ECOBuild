"""拡張：作業空間のエージェント（Claude Code 等。ecoagent を使う）。

- AgentModule：Module に重ねる（本体＋拡張が class Module(AgentModule, ContainerModule, ecobuild.Module) とする）。
  作業空間のエージェントの起動・会話・起動のときに渡す文書（agent_briefing）。起動するのは登録（registry）のエージェント。
- agents：起動したエージェント1人ごとの記録（ID・登録・親・持ち主か手伝いか）。registry：エージェントの登録。
  mcp：エージェント専用の MCP サーバー（許したツールだけを渡す）。
- children：子のエージェント（手伝い・子タスク）を扱うツール。serve：このPCの係（エージェントの間の取り次ぎ）。app：係が持つアプリ用の起動のエージェント
  （AI が起動したもの。claude -p の stream-json）。status：エージェントごとの状態の置き場所（画面を持つアプリへ知らせる）。
  inside：コンテナの中のエージェント（コンテナに足すもの FEATURE）。
  tokens：中のエージェントのログイン。
- 作業空間のコンテナ（ecobuild_container）は公開の口だけを使う（向きはエージェント → コンテナ。コンテナはエージェントを知らない）。
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import ecoagent
import ecobuild_container as container
from ecoagent.guard import CHANGE, CONFIRM, HUMAN, READ  # noqa: F401（コマンドの重さ。CLI の _effects が使う）
from ecobuild.errors import EcoBuildError, WorkError, operation
from ecobuild.fsutil import locked

from . import agents, app, children, host, inside, registry, rules, skills, status
from .agents import AgentRecord
from .errors import ErrorCode, from_ecoagent
from .inside import FEATURE as CONTAINER_FEATURE
from .results import AgentConversations

AGENT_AREA = ".ecobuild/ai"   # 作業空間の中のエージェント用の置き場所（コミットしない。prepare_agent_area）
EXCLUDE_LOCK = "ecobuild-exclude.lock"   # git の除外（info/exclude）に書き足す間のロック（git の <名前>.lock とは別の名前）
GUIDE_FILE = "guide.md"       # エージェントの置き場所の中：起動のときに渡す文（--append-system-prompt-file）
MCP_FILE = "mcp.json"         # エージェントの置き場所の中：エージェント専用の MCP サーバーの設定（--mcp-config）
SKILLS_FOLDER = "skills"      # エージェントの置き場所の中：使えるスキル（<ここ>/.claude/skills/<名前>/。--add-dir）
REGISTRATION_FILE = "registration.json"   # エージェントの置き場所の中：このPCで解決した登録（中の MCP サーバーが読む）
# シェルの関所（ecobuild agent guard。中の ECOBuild）：シェルの ecobuild・gh・git の書き込みを止める（ecobuild_agent.guard）
GUARD_HOOK = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "ecobuild agent guard"}]}]}}
SESSION_VARIABLE = "CLAUDE_CODE_SESSION_ID"   # Claude Code が道具に渡す、いまの会話の ID（起動を頼んだ会話）
RESUME_FLAGS = ("--resume", "-r")
CONTINUE_FLAGS = ("--continue", "-c")

# config で扱う項目 → 説明（本体＋拡張が、本体と型の項目に足す）。モデルは登録ごと（registry）
CONFIG_KEYS = {
    "operator_style": "オペレーターの話し方（口調・答え方。例：やさしい敬語で短く。空なら指定なし）",
    inside.DENY_KEY: "コンテナの中のエージェントに使わせない道具・コマンド（Claude Code の許可の規則を ; で区切る。"
                     "例 Bash(git push --force:*);WebFetch。既定はなし＝すべて使える）",
}


def in_use_source(roots) -> list[list[str]]:
    """作業空間を使っているもの（ecobuild.usage.add_source）：その作業空間で動いているエージェント
    （agent start の3つの形・係が持つもの。エージェントごとの running.json の pid が生きている間）。"""
    found: list[list[str]] = [[] for _ in roots]
    for index, root in enumerate(roots):
        for record in agents.in_workspace(root):
            folder = status.directory(record.id)
            pid = status.running_pid(folder) if folder is not None else None
            if pid is None:
                continue
            held = status.running_mode(folder) == status.APP
            who = f"エージェント「{record.name}」（{record.id}）"
            found[index].append((f"{who}を係が持っています" if held else f"この作業空間で{who}が動いています") + f"（pid {pid}）")
    return found


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


class AgentModule:
    """作業空間のエージェント。いつもコンテナの中で確認なしに起動する（コンテナにしていない作業空間は、起動の前に自動で
    コンテナにする。使わせないものは設定 agent_deny）。1つの作業空間に、タスクの持ち主と手伝いが何人もいてよい
    （エージェントごとに ID・置き場所・受け箱・guide.md を分ける）。"""

    def _ensure_container(self, progress=lambda message: None) -> None:
        """エージェントはコンテナの中で動かす：コンテナにしていない作業空間は、container on（選ぶだけ。コンテナは起動のときに作る）。"""
        if not container.enabled(self.root):
            progress("エージェントはコンテナの中で動かすので、この作業空間をコンテナにします（container on）")
            container.choose(self.root, True, command=self.command)

    # ---- 起動 ---------------------------------------------------------------------------------------------
    def start_agent(self, registration: str = "", *, task: int | None = None, parent: str | None = None,
                    kind: str = agents.OWNER, here: bool = False, app: bool = False, program=None,
                    prompt: str | None = None, source=None, progress=lambda message: None) -> AgentRecord:
        """登録 registration のエージェントを、タスクの作業空間のルートで起動する。タスクブランチでだけ（エージェントは
        タスクの作業をするもの）。task：タスクの番号（省けば今の作業空間のタスク。ほかのタスクならその作業空間で）。
        parent：親のエージェントの ID。kind：owner（タスクの持ち主）か helper（手伝い：同じ作業空間・コミットしない）。
        既定は新しい画面で起動して戻る。here：この端末で動かして終わるまで待つ（run_agent）。app：画面なしで、このPCの
        係に動かしてもらう（係が持つ）。program：起動するコマンド（既定は claude。claude --resume <会話> なら、その会話の
        エージェントを続きから）。prompt：最初の発言（省けば登録の first_prompt）。source：コンテナのイメージに入れる ECOBuild。"""
        other = self._task_module(task)
        if other is not None:
            return other.start_agent(registration, parent=parent, kind=kind, here=here, app=app, program=program,
                                     prompt=prompt, source=source, progress=progress)
        if here:
            record, _ = self._run_here(registration, parent=parent, kind=kind, program=program, prompt=prompt,
                                       source=source, progress=progress)
            return record
        if app:
            return self._start_app(registration, parent=parent, kind=kind, prompt=prompt, progress=progress)
        task_branch = self._task_for_agent()
        self._ensure_container(progress)
        record, command, folder, _ = self._prepared(registration, task_branch, parent, kind, program, prompt, source,
                                                     progress, app=False)
        session = inside.start_agent(self.root, command, deny=inside.deny(self.root), command=self.command,
                                     source=source, progress=progress, agent_id=record.id)
        status.started(folder, session.pid)   # 動いているか・止める（子の様子・起動し直す）
        return record

    def run_agent(self, registration: str = "", *, task: int | None = None, parent: str | None = None,
                  kind: str = agents.OWNER, program=None, prompt: str | None = None, source=None,
                  progress=lambda message: None) -> int:
        """この端末で動かして、終わるまで待つ（終了コード。start_agent と同じく、コンテナの中で）。画面を持つ別のアプリ
        （GUI のエージェントの窓）が、自分の端末の中で動かすときに使う。Claude Code なら、状態（モデル・使用量・返答の
        終わり）を書き出させ、その置き場所を端末に知らせる（status。画面を持つアプリが読む）。"""
        other = self._task_module(task)
        if other is not None:
            return other.run_agent(registration, parent=parent, kind=kind, program=program, prompt=prompt,
                                   source=source, progress=progress)
        return self._run_here(registration, parent=parent, kind=kind, program=program, prompt=prompt, source=source,
                              progress=progress)[1]

    def _run_here(self, registration, *, parent, kind, program, prompt, source, progress) -> tuple[AgentRecord, int]:
        task_branch = self._task_for_agent()
        self._ensure_container(progress)
        record, command, folder, claude = self._prepared(registration, task_branch, parent, kind, program, prompt,
                                                          source, progress, app=True)
        if claude:
            status.announce(folder)
            status.started(folder, os.getpid())   # このプロセスが終わるまでエージェントが動いている
        try:
            code = inside.start_agent(self.root, command, deny=inside.deny(self.root), command=self.command,
                                      source=source, progress=progress, here=True, agent_id=record.id)
        except ecoagent.AgentError as error:
            raise from_ecoagent(error) from error
        finally:
            if claude:
                status.ended(folder, os.getpid())
        return record, code

    def _start_app(self, registration, *, parent, kind, prompt, progress) -> AgentRecord:
        """画面なし（アプリ用の起動）：記録を作り、このPCの係に起動を頼む（係が app_launch で起動して持つ）。"""
        task_branch = self._task_for_agent()
        self._ensure_container(progress)
        record = self._record(registration, task_branch, parent, kind, None)
        args = ["agent", "start", "--app", "--id", record.id, *(["--prompt", prompt] if prompt else [])]
        doc = children.forward(children.human_requests(record.id), {"args": [*args, "--json"], "cwd": "."},
                               progress=progress)
        if not doc.get("ok"):
            error = doc.get("error") or {}
            raise EcoBuildError(error.get("code") or ErrorCode.AGENT_ERROR, error.get("message") or "係での起動に失敗しました。",
                                hint=error.get("hint"), details=error.get("details"))
        return agents.load(record.id)

    def app_launch(self, agent_id: str, *, resume: str = "", prompt: str | None = None, source=None,
                   progress=lambda message: None) -> app.Launch:
        """記録のあるエージェント agent_id の、アプリ用の起動（係が持つ。claude -p の stream-json）のしかた。コンテナで
        動かす（コンテナにしていなければ、自動でコンテナにする）。タスクブランチでだけ。resume：その会話の続きから（なければ
        新しい会話）。会話の ID・モデル・使い方の文・設定は対話型と同じ作り方（statusLine・返答の終わりのフックは付けない：
        係が出来事を読む）。最初の発言は標準入力から入れる（係。prompt は使わない）。"""
        task_branch = self._task_for_agent()
        self._ensure_container(progress)
        record = agents.load(agent_id)
        if not _same(record.workspace, self.root):
            raise EcoBuildError(ErrorCode.AGENT_ERROR, f"エージェント {agent_id} は、この作業空間のものではありません。",
                                hint=f"作業空間は {record.workspace} です。")
        self._no_other_agent(record)
        command = ("claude", *app.FLAGS, *(("--resume", resume) if resume else ()))
        record, command = self._session(record, command)
        session = resume or record.session
        folder = status.prepare(record.folder, self.root)
        command = self._options(record, command, "")
        command = (*command, *limits(self._registration(record)))
        command = (*command, "--settings", self._status_settings(folder, record, app=False, streamed=True))
        command = self._briefed(command, folder, True, task_branch, record)
        tag = uuid.uuid4().hex[:16]
        argv, env = inside.agent_launch(self.root, command, deny=inside.deny(self.root), command=self.command,
                                        source=source, progress=progress, tty=False, stdin=True, tag=tag,
                                        agent_id=record.id)
        root, program = self.root, self.command
        return app.Launch(root, folder, tuple(argv), env, session, record.id, record.registration,
                          kill=lambda: container.stop_tagged(root, tag, command=program))

    def _prepared(self, registration, task_branch, parent, kind, program, prompt, source, progress, *, app: bool):
        """起動の準備：記録（続きからなら会話の記録）・会話の ID・モデル・最初の発言・設定・使い方の文・MCP の設定。
        (記録, コマンド, 置き場所, Claude Code か) を返す。"""
        command = tuple(program.split() if isinstance(program, str) else program or ()) or ecoagent.DEFAULT_COMMAND
        claude = command[:1] == ("claude",)

        def latest() -> str:
            container.start(self.root, command=self.command, source=source, progress=progress)
            found = self.agent_conversations(1).conversations
            return found[0].id if found else ""
        resumed = resumed_session(command, latest) if claude else None
        record = agents.by_session(resumed) if resumed else None
        if record is not None and not _same(record.workspace, self.root):
            raise EcoBuildError(ErrorCode.AGENT_ERROR,
                                f"会話 {resumed} は、ほかの作業空間のエージェント「{record.name}」（{record.id}）のものです。",
                                hint=f"その作業空間（{record.workspace}）で起動してください。")
        if record is None:
            record = self._record(registration, task_branch, parent, kind, resumed or "")
        self._not_held_by_serve(record)
        self._no_other_agent(record)
        folder = status.prepare(record.folder, self.root)
        if not claude:
            return record, command, folder, False
        self.prepare_agent_area()
        record, command = self._session(record, command)
        first = prompt if prompt is not None else ("" if resumed is not None else self._registration(record).first_prompt)
        command = self._options(record, command, first)
        command = (*command, "--settings", self._status_settings(folder, record, app=app))
        return record, self._briefed(command, folder, True, task_branch, record), folder, True

    def _record(self, registration: str, task_branch, parent, kind, session: str) -> AgentRecord:
        """新しいエージェントの記録（登録を確かめてから）。"""
        if not registration:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "起動するエージェントの登録を指定してください。",
                                hint="登録は agent registry list で見られます（agent start --as <登録名>）。")
        found = registry.effective(registration, self.root)
        if parent:
            agents.load(parent)   # 親が分かること
        return agents.create(registration=found.name, workspace=self.root, kind=kind, parent=parent,
                             task={"number": task_branch.number, "branch": task_branch.branch}, model=found.model,
                             session=session, owner_session=os.environ.get(SESSION_VARIABLE, "").strip())

    @staticmethod
    def _registration(record: AgentRecord) -> registry.Registration:
        """記録の登録（その作業空間のモジュールの、作成元に取り込まれたもの）。消された登録なら、文書なしの空のもの。"""
        return children._registration(record)

    @staticmethod
    def _session(record: AgentRecord, command: tuple[str, ...]) -> tuple[AgentRecord, tuple[str, ...]]:
        """新しい会話なら ID を決めて渡し（--session-id）、記録に書く。続きからならその会話を記録に書く。"""
        resumed = resumed_session(command, lambda: "")
        if resumed:
            return (agents.update(record.id, session=resumed) if record.session != resumed else record), command
        if resumed is not None or any(w in command or any(x.startswith(w + "=") for x in command)
                                      for w in (*CONTINUE_FLAGS, "--session-id")):
            return record, command
        session = str(uuid.uuid4())
        return agents.update(record.id, session=session), (*command, "--session-id", session)

    @staticmethod
    def _options(record: AgentRecord, command: tuple[str, ...], prompt: str) -> tuple[str, ...]:
        """登録のモデル（指定済みなら足さない）と、最初の発言（claude のすぐ後ろ：--disallowedTools 等のいくつも値を
        取る引数の後ろに置くと、その値として読まれる）。"""
        if record.model and "--model" not in command:
            command = (*command, "--model", record.model)
        return (command[0], prompt, *command[1:]) if prompt.strip() else command

    def _task_module(self, task: int | None):
        """task がほかのタスクなら、その作業空間の Module（今の作業空間のタスクなら None）。"""
        if task is None:
            return None
        try:
            current = self._task_for_agent()
        except WorkError:
            current = None
        if current is not None and current.number == task:
            return None
        places = self.task_workspaces() if hasattr(self, "task_workspaces") else {}   # 本体の口（作業空間の一覧）
        path = places.get(task)
        if path is None:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"タスク #{task} の作業空間がありません。",
                                hint=f"先に {operation(self.command, f'task start {task}')} で作業空間を作ってください。")
        return type(self).find(path)

    def _task_for_agent(self):
        """エージェントを起動する作業空間の今のタスク（タスクブランチでだけ起動する）。"""
        return self.require_task_branch("エージェントの起動")

    def _not_held_by_serve(self, record: AgentRecord) -> None:
        """係がアプリ用で動かしているなら、対話型では起動しない（同じ会話を2つが書き換えないように）。"""
        if status.running_mode(record.folder) == status.APP:
            raise EcoBuildError(ErrorCode.AGENT_ERROR,
                                f"エージェント「{record.name}」（{record.id}）は、係がアプリ用で動かしています。",
                                hint="人が引き取るには agent takeover <ID>（人がアプリ用で起動したものは agent stop <ID>）。")

    def _no_other_agent(self, record: AgentRecord, wait: float = 3.0) -> None:
        """同じエージェント（ID）がもう動いているなら、2重に起動しない（同じ会話・受け箱・状態を共有してしまう）。
        同じ作業空間のほかのエージェントは止めない。起動し直し（前のプロセスを止めた直後）で誤って止めないよう、
        終わるのを wait 秒まで待つ。"""
        folder = record.folder
        end = time.monotonic() + wait
        pid = status.running_pid(folder)
        while pid is not None and pid != os.getpid() and time.monotonic() < end:
            time.sleep(0.1)
            pid = status.running_pid(folder)
        if pid is None or pid == os.getpid():
            return
        data = status.read(folder / status.RUNNING)
        at = data.get("at") if isinstance(data, dict) else None
        since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(at)) if isinstance(at, (int, float)) else "不明"
        raise EcoBuildError(ErrorCode.AGENT_ERROR,
                            f"エージェント「{record.name}」（{record.id}）は、もう動いています（pid {pid}・起動 {since}）。",
                            hint="同じエージェントは2重に起動しません（同じ会話・受け箱を共有してしまいます）。その会話を"
                                 "続けるか、別のエージェントを起動してください。")

    def before_close_workspace(self, path) -> list[str]:
        """作業空間 path を閉じられないわけ（本体の口に足す）：閉じていない子タスクの持ち主（動いているエージェントは、
        本体が ecobuild.usage〔in_use_source〕で確かめる）。"""
        found = list(super().before_close_workspace(path)) if hasattr(super(), "before_close_workspace") else []
        for record in agents.in_workspace(Path(path)):
            open_tasks = [child for child in agents.children(record.id) if child.kind == agents.OWNER and child.task
                          and not _same(child.workspace, record.workspace)]
            if open_tasks:
                found.append(f"エージェント「{record.name}」（{record.id}）に閉じていない子タスクがあります："
                             + "、".join(f"#{child.task.get('number')}「{child.name}」" for child in open_tasks))
        return found

    def _status_settings(self, folder: Path, record: AgentRecord, *, app: bool, streamed: bool = False) -> str:
        """状態を書き出させる --settings（status）と、シェルの関所（GUARD_HOOK）。コンテナの中から見た置き場所と中の
        Python。streamed：アプリ用の起動。"""
        return status.settings_argument(folder, status.inside(record.id), "python3", GUARD_HOOK, app=app,
                                        streamed=streamed)

    # ---- 会話 -----------------------------------------------------------------------------------------------
    def agent_conversations(self, limit: int = 20) -> AgentConversations:
        """作業空間でのエージェントの会話（新しい順。続きから再開するものを選ぶ）。タスクブランチでなくても読める。
        コンテナにした作業空間では、中の会話（すべてのコンテナで共有する設定の場所にある。中の場所はどれも同じなので、
        今のブランチでの会話だけ）。コンテナが動いていなければ読まない（note にわけ）。"""
        if not container.enabled(self.root):
            found, note = tuple(ecoagent.conversations(self.root, limit=limit)), ""
        else:
            found, note = inside.agent_conversations(self.root, self.repository.git.current_branch() or "", limit,
                                                     command=self.command)
        return AgentConversations(self.root, found, note, _running(found))

    # ---- 渡すもの -------------------------------------------------------------------------------------------
    def agent_briefing(self, task, record: AgentRecord) -> str:
        """起動のときにエージェントへ渡す文：共通の前置き（モジュール・タスク・作業空間・持ち主か手伝いか・持ち主は誰か）、
        登録の文書、モジュールの決まり（全エージェント共通の文。登録と同じく作成元に取り込まれたもの：rules）。
        ECOBuild の操作はツール（MCP）なので、CLI の手順（agent guide）は入れない。"""
        lines = [
            "# ECOBuild から：この作業空間での作業のしかた",
            "",
            f"- ここは ECOBuild のモジュール「{self.config.name}」の作業空間（{container.workdir(self.root)}）で、"
            f"タスクブランチ `{task.branch}`（タスク #{task.number}）にいます。",
            f"- あなたはエージェント「{record.name}」（ID {record.id}・登録「{record.registration}」）です。",
            *self._owner_lines(record),
            "- ECOBuild の操作（タスク・ビルド・テスト・実行・提出・子のエージェント）は、MCP のツール（ecobuild）で行います。"
            "シェルから ecobuild・gh を使わず、git で書き込む操作（commit・push・switch 等）もしません。型のツール（テスト・"
            "ビルドの道具）も直接使わず、build・test・run のツールで。",
            "- リポジトリの AGENTS.md にある CLI の手順は、外から ECOBuild を使うときのものです。ここでは、"
            "そこにある `ecobuild` のコマンドを同じ名前のツール（task commit → task_commit 等）に読み替えます。",
            f"- `{AGENT_AREA}/` はエージェント用の置き場所です（コミットされません）。メモ・下書き・調べた結果・一時ファイルは、"
            "ここへ自由に書いて構いません。作業の成果（コード・文書）はここに置かず、モジュールの中の本来の場所へ。",
            "",
        ]
        found = self._registration(record)
        document = found.document.strip()
        return "\n".join([*lines, *([document, ""] if document else []), *loop_lines(found, task),
                          *self._module_rules(record)])

    @staticmethod
    def _owner_lines(record: AgentRecord) -> list[str]:
        parent = _load_or_none(record.parent)
        by = f"親のエージェント「{parent.name}」（{parent.id}）" if parent else ("親のエージェント" if record.parent else "人")
        if record.kind == agents.HELPER:
            owner = parent if parent is not None and parent.kind == agents.OWNER and _same(parent.workspace, record.workspace) \
                else next((r for r in agents.in_workspace(Path(record.workspace)) if r.kind == agents.OWNER), None)
            who = f"「{owner.name}」（{owner.id}）" if owner else "このタスクの持ち主"
            return [f"- あなたは手伝いです（{by}が起動しました）。この作業空間とタスクは{who}のもので、コミット・提出は"
                    "持ち主がします。あなたはコミット・提出をせず、頼まれたことを終えたら親に知らせます。"]
        return [f"- あなたはこのタスクの持ち主です（{by}が起動しました）。コミット・提出はあなたがします。"]

    def _module_rules(self, record: AgentRecord) -> list[str]:
        """モジュールの決まり（rules）：全エージェント共通の文（役ごとの文は登録の文書）。"""
        common = rules.in_force(self.root).strip()
        return ["## このモジュールの決まり（全エージェント共通）", "", common, ""] if common else []

    def prepare_agent_area(self) -> Path:
        """エージェント用の置き場所（AGENT_AREA）を作り、この clone の git の除外（info/exclude）に足す。リポジトリの
        ファイルは変えないので、コミットは要らない（今あるモジュールでもすぐ使える）。"""
        area = self.root / AGENT_AREA
        area.mkdir(parents=True, exist_ok=True)
        try:
            found = self.repository.git.run("rev-parse", "--git-path", "info/exclude", check=False)
        except WorkError:
            return area
        if found.ok and found.stdout.strip():
            exclude = Path(found.stdout.strip())
            exclude = exclude if exclude.is_absolute() else self.root / exclude
            line = f"/{AGENT_AREA}/"
            if line in _read(exclude).splitlines():
                return area
            # 子を並べて作ると同時に書き足しに来る：1つずつ、読んだものに足して置き換える（書きかけを読ませない）
            with locked(exclude.with_name(EXCLUDE_LOCK)):
                text = _read(exclude)
                if line not in text.splitlines():
                    temporary = exclude.with_name(f"{exclude.name}.{os.getpid()}.tmp")
                    temporary.write_text(text + ("" if not text or text.endswith("\n") else "\n")
                                         + f"# ECOBuild：エージェント用の置き場所（コミットしない）\n{line}\n", encoding="utf-8")
                    _replace(temporary, exclude)
        return area

    def _briefed(self, command: tuple[str, ...], folder: Path, boxed: bool, task,
                 record: AgentRecord) -> tuple[str, ...]:
        """Claude Code なら、使い方の文をファイル（置き場所の guide.md）にして --append-system-prompt-file で、エージェント
        専用の MCP サーバーを --mcp-config（置き場所の mcp.json）と --strict-mcp-config で渡す（長い文を引数にしない：
        claude.cmd は cmd.exe を通る）。"""
        if command[:1] != ("claude",):
            return command
        self.prepare_agent_area()
        where = status.inside(record.id) if boxed else folder.as_posix()
        if "--append-system-prompt-file" not in command:
            (folder / GUIDE_FILE).write_text(self.agent_briefing(task, record), encoding="utf-8", newline="\n")
            command = (*command, "--append-system-prompt-file", f"{where}/{GUIDE_FILE}")
        if "--mcp-config" not in command:
            if boxed:   # コンテナの中からはこのPCの登録が見えないので、このPCで解決した登録を写して渡す
                (folder / REGISTRATION_FILE).write_text(
                    json.dumps(registry.to_data(self._registration(record)), ensure_ascii=False, indent=1),
                    encoding="utf-8", newline="\n")
            (folder / MCP_FILE).write_text(json.dumps(self.mcp_config(record, boxed), ensure_ascii=False, indent=1),
                                           encoding="utf-8", newline="\n")
            command = (*command, "--mcp-config", f"{where}/{MCP_FILE}", "--strict-mcp-config")
        # 使えるスキル（作成元に取り込まれたもののうち、登録の skills に合うもの）を置き場所に写し、--add-dir で渡す
        # （Claude Code は --add-dir のフォルダーの .claude/skills を読む）
        if skills.provide(self.root, self._registration(record).skills, folder / SKILLS_FOLDER / ".claude" / "skills") \
                and "--add-dir" not in command:
            command = (*command, "--add-dir", f"{where}/{SKILLS_FOLDER}")
        return command

    def mcp_config(self, record: AgentRecord, boxed: bool = True) -> dict:
        """エージェント専用の MCP サーバー（ecobuild agent mcp）の設定。呼び手は引数で固定する（ツールの引数では名乗らせない）。
        コンテナの中では、中の ECOBuild（層に入っている ecobuild）で、中の作業空間の場所を渡す。"""
        workspace = container.workdir(self.root) if boxed else str(self.root)
        args = ["agent", "mcp", "--agent", record.id, "--registration", record.registration, "--kind", record.kind,
                "--workspace", workspace]
        if boxed:   # このPCで解決した登録（_briefed が置き場所に写す。中の ECOBUILD_HOME には登録がない）
            args += ["--registration-file", f"{status.inside(record.id)}/{REGISTRATION_FILE}"]
        if boxed and inside.host_run(self.root):   # このPCで実行するツール（container set --host-run on）
            args.append("--host-run")
        program, before = ("ecobuild", []) if boxed else (sys.executable, ["-m", "ecobuild_cli"])
        return {"mcpServers": {"ecobuild": {"type": "stdio", "command": program, "args": [*before, *args]}}}


def limits(registration: registry.Registration) -> tuple[str, ...]:
    """登録の上限を Claude Code の引数に（アプリ用の起動＝claude -p でだけ効く：対話型は人が見て止める）。"""
    found: tuple[str, ...] = ()
    if registration.max_turns:
        found += ("--max-turns", str(registration.max_turns))
    if registration.max_cost:
        found += ("--max-budget-usd", f"{registration.max_cost:g}")
    return found


def loop_lines(registration: registry.Registration, task) -> list[str]:
    """起動の文の「改善のループと止める条件」の節：登録で決めた値だけ（進め方は登録の文書に書く。同じことを二重に
    書かない）。何も決めていなければ空。"""
    r = registration
    if not any(getattr(r, key) for key in registry.LOOP_FIELDS):
        return []
    lines = ["## 改善のループと止める条件（登録で決めた値）", "",
             f"- 評価：{f'`{r.evaluation}`' if r.evaluation else '任された仕事に書かれたもの（なければ build・test）'}"]
    if r.max_rounds:
        lines.append(f"- 評価し直す回数の上限：{r.max_rounds} 回")
    if r.max_turns:
        lines.append(f"- ターン数の上限：{r.max_turns}（ECOBuild が止めます）")
    if r.max_cost:
        lines.append(f"- 費用の上限：{r.max_cost:g} ドル（ECOBuild が止めます）")
    if r.lessons:
        folder = r.lessons.strip().replace("\\", "/").rstrip("/")
        lines.append(f"- 教訓の記録先：`{folder}/{task.number}.md`（作業と一緒にコミット。始める前に `{folder}/` を読む）")
    else:
        lines.append("- 教訓の記録先：報告の「教訓」の節")
    return [*lines, ""]


def _running(conversations) -> tuple[dict, ...]:
    """会話のうち、今動いているエージェントのもの（続きから起動すると、同じエージェントが2重になるので断る）。"""
    found = []
    for conversation in conversations:
        record = agents.by_session(conversation.id)
        if record is not None and status.running_pid(record.folder) is not None:
            found.append({"session": conversation.id, "agent": record.id, "name": record.name})
    return tuple(found)


def _same(a, b) -> bool:
    try:
        return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))
    except OSError:
        return False


def _load_or_none(agent_id: str | None) -> AgentRecord | None:
    if not agent_id:
        return None
    try:
        return agents.load(agent_id)
    except EcoBuildError:
        return None


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _replace(temporary: Path, path: Path) -> None:
    for attempt in range(5):   # Windows：ほかのコマンドが読んでいる間は置き換えられない
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 4:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


__all__ = ["AGENT_AREA", "AgentConversations", "AgentModule", "AgentRecord", "CONFIG_KEYS", "CONTAINER_FEATURE",
           "ErrorCode", "agents"]
