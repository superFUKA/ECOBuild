"""拡張：作業空間のエージェント（Claude Code 等。ecoagent を使う）。

- AgentModule：Module に重ねる（本体＋拡張が class Module(AgentModule, ContainerModule, ecobuild.Module) とする）。
  作業空間のエージェントの起動・会話・起動のときに渡す使い方（agent_briefing）。
- team：進行役と作業役。serve：このPCの係（エージェントの間の取り次ぎ）。status：画面を持つアプリへ知らせる状態。
  operator：オペレーター（ECOBuild の操作係）。inside：コンテナの中のエージェント（コンテナに足すもの FEATURE）。
  tokens：中のエージェントのログイン。
- 作業空間のコンテナ（ecobuild_container）は公開の口だけを使う（向きはエージェント → コンテナ。コンテナはエージェントを知らない）。
"""

from __future__ import annotations

from pathlib import Path

import ecoagent
import ecobuild_container as container
from ecobuild import settings as _settings
from ecobuild.errors import WorkError

from . import inside, status, team
from .errors import ErrorCode, from_ecoagent
from .inside import FEATURE as CONTAINER_FEATURE
from .results import AgentConversations, AgentStarted

AGENT_AREA = ".ecobuild/ai"   # 作業空間の中のエージェント用の置き場所（コミットしない。prepare_agent_area）

# config で扱う項目 → 説明（本体＋拡張が、本体と型の項目に足す）
CONFIG_KEYS = {
    "operator_style": "オペレーターの話し方（口調・答え方。例：やさしい敬語で短く。空なら指定なし）",
    "agent_style": "作業用のエージェントの話し方（口調・答え方。空なら指定なし）",
    "agent_lead_model": "進行役のエージェントのモデル（Claude Code の --model。例 opus・sonnet。空なら Claude Code の既定）",
    "agent_worker_model": "作業役のエージェントのモデル（Claude Code の --model。例 sonnet・haiku。空なら Claude Code の既定。"
                          "作業役ごとに agent team start --model でも指定できる）",
    inside.DENY_KEY: "コンテナの中のエージェントに使わせない道具・コマンド（Claude Code の許可の規則を ; で区切る。"
                     "例 Bash(git push --force:*);WebFetch。既定はなし＝すべて使える）",
}


class AgentModule:
    """作業空間のエージェント。コンテナにした作業空間では、コンテナの中で確認なしに起動する（使わせないものは設定 agent_deny）。"""

    def start_agent(self, command=ecoagent.DEFAULT_COMMAND, *, source=None,
                    progress=lambda message: None, role: str = "", prompt: str = "") -> AgentStarted:
        """作業空間のルート（モジュールのルート）で、エージェントを新しい画面で起動する。タスクブランチでだけ
        （エージェントはタスクの作業をするもの。作業空間がタスクブランチでなければ起動しない）。
        source：コンテナのイメージに入れる ECOBuild（container.start と同じ）。Claude Code には、ECOBuild の使い方
        （agent_briefing）を最初から渡す。role：進行役（lead）か作業役（worker。既定は作業空間の記録、なければ作業役）。
        prompt：最初の発言。"""
        boxed = container.enabled(self.root)
        task = self.require_task_branch("エージェントの起動")
        role = self._role(role, tuple(command), boxed, source, progress)
        command = self._for_role(tuple(command), role, prompt)
        folder = status.prepare(container.name(self.root), self.root)
        if command[:1] == ("claude",):   # 返答の終わりを書き出させ（係が進行役に知らせる）、受け箱はフックが届ける
            command = (*command, "--settings", self._status_settings(folder, boxed, app=False))
        command = self._briefed(command, folder, boxed, task, role)
        if not boxed:
            try:
                session = ecoagent.start(self.root, command)
            except ecoagent.AgentError as error:
                raise from_ecoagent(error) from error
        else:
            session = inside.start_agent(self.root, command, deny=inside.deny(self.root), command=self.command,
                                         source=source, progress=progress)
        return AgentStarted(session.pid, session.command, session.directory)

    def run_agent(self, command=ecoagent.DEFAULT_COMMAND, *, source=None, progress=lambda message: None,
                  role: str = "", prompt: str = "") -> int:
        """この端末で動かして、終わるまで待つ（終了コード。start_agent と同じく、コンテナならその中で）。画面を持つ別の
        アプリ（GUI のエージェントの窓）が、自分の端末の中で動かすときに使う。Claude Code なら、状態（モデル・使用量・
        返答の終わり）を書き出させ、その置き場所を端末に知らせる（status。画面を持つアプリが読む）。"""
        boxed = container.enabled(self.root)
        task = self.require_task_branch("エージェントの起動")
        role = self._role(role, tuple(command), boxed, source, progress)
        command = self._for_role(tuple(command), role, prompt)
        if command[:1] == ("claude",):
            folder = status.prepare(container.name(self.root), self.root)
            status.announce(folder)
            command = (*command, "--settings", self._status_settings(folder, boxed, app=True))
            command = self._briefed(command, folder, boxed, task, role)
        if boxed:
            return inside.start_agent(self.root, command, deny=inside.deny(self.root), command=self.command,
                                      source=source, progress=progress, here=True)
        try:
            return ecoagent.run(self.root, command)
        except ecoagent.AgentError as error:
            raise from_ecoagent(error) from error

    @staticmethod
    def _status_settings(folder: Path, boxed: bool, *, app: bool) -> str:
        """状態を書き出させる --settings（status）。コンテナの中からは、マウントした所と中の Python。"""
        where, python = (status.INSIDE, "python3") if boxed else (folder.as_posix(), status.host_python())
        return status.settings_argument(folder, where, python, app=app)

    def agent_conversations(self, limit: int = 20) -> AgentConversations:
        """作業空間でのエージェントの会話（新しい順。続きから再開するものを選ぶ）。タスクブランチでなくても読める。
        コンテナにした作業空間では、中の会話（すべてのコンテナで共有する設定の場所にある。中の場所はどれも同じなので、
        今のブランチでの会話だけ）。コンテナが動いていなければ読まない（note にわけ）。"""
        if not container.enabled(self.root):
            return AgentConversations(self.root, tuple(ecoagent.conversations(self.root, limit=limit)))
        found, note = inside.agent_conversations(self.root, self.repository.git.current_branch() or "", limit,
                                                 command=self.command)
        return AgentConversations(self.root, found, note)

    def agent_briefing(self, task, role: str = team.WORKER) -> str:
        """起動のときにエージェントへ渡す文：今の作業空間・タスクブランチ、役（進行役・作業役）の決まりと、ECOBuild の
        使い方（agent guide）。AGENTS.md がないモジュールでも、最初から ECOBuild のコマンドで作業させるため。"""
        program = self.command or "ecobuild"
        return "\n".join([
            "# ECOBuild から：この作業空間での作業のしかた",
            "",
            f"- ここは ECOBuild のモジュール「{self.config.name}」の作業空間で、タスクブランチ `{task.branch}`"
            f"（タスク #{task.number}）にいます。タスクの内容は `{program} task status` で確かめてください。",
            f"- 作業は下の手順のとおり、`{program}` のコマンドで行います。とくに、ビルド・テスト・実行は必ず "
            f"`{program} build`・`{program} test`・`{program} run`（提出の前は `{program} check`）。"
            "cmake・ninja・msbuild・pytest などを直接使いません。",
            f"- `{AGENT_AREA}/` はエージェント用の置き場所です（コミットされません）。メモ・下書き・調べた結果・一時ファイルは、"
            "コマンドを使わずにここへ自由に書いて構いません。作業の成果（コード・文書）はここに置かず、モジュールの中の本来の場所へ。",
            "",
            *team.briefing(self.root, role, program),
            *self._style(),
            self.agent_guide().text,
        ])

    @staticmethod
    def _style() -> list[str]:
        """ユーザーが決めた話し方（設定 agent_style）。"""
        style = _settings.load_config().get("agent_style", "").strip()
        return ["## 話し方（ユーザーの指定）", "", style, "",
                "（口調・言い回し・呼び方だけを変える。手順・確認・決まり・報告の中身（コマンド・結果・エラー・数字）は変えず、正確に伝える。コミット・PR・コード・文書など、成果物の文には使わない）", ""] if style else []

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
            text = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
            if line not in text.splitlines():
                exclude.parent.mkdir(parents=True, exist_ok=True)
                exclude.write_text(text + ("" if not text or text.endswith("\n") else "\n")
                                   + f"# ECOBuild：エージェント用の置き場所（コミットしない）\n{line}\n", encoding="utf-8")
        return area

    def _role(self, chosen: str, command: tuple[str, ...], boxed: bool, source, progress) -> str:
        """起動する役：指定、なければ続きから起動する会話の役（起動のときに覚えたもの。team.ROLES_FILE）、なければ
        作業空間の記録、なければ作業役。--continue は、いちばん新しい会話（コンテナなら動かしてから読む）。"""
        if chosen:
            return team.role_of(self.root, chosen)

        def latest() -> str:
            if boxed:
                container.start(self.root, command=self.command, source=source, progress=progress)
            found = self.agent_conversations(1).conversations
            return found[0].id if found else ""
        session = team.resumed_session(command, latest)
        return team.role_of(self.root, team.remembered_roles(self.root).get(session, "") if session else "")

    def _for_role(self, command: tuple[str, ...], role: str, prompt: str) -> tuple[str, ...]:
        """役のモデル・使わせない道具（team.agent_options）と、最初の発言（claude のすぐ後ろ：--disallowedTools 等の
        いくつも値を取る引数の後ろに置くと、その値として読まれる）。"""
        if command[:1] == ("claude",):
            self.prepare_agent_area()   # 覚えた役（.ecobuild/ai）をコミットの対象に出さない
        command = team.new_session(self.root, role, team.agent_options(self.root, role, command))
        return (command[0], prompt, *command[1:]) if prompt.strip() and command[:1] == ("claude",) else command

    def _briefed(self, command: tuple[str, ...], folder: Path, boxed: bool, task,
                 role: str = team.WORKER) -> tuple[str, ...]:
        """Claude Code なら、使い方の文をファイル（状態の置き場所の guide.md）にして --append-system-prompt-file で渡す
        （長い文を引数にしない：claude.cmd は cmd.exe を通る）。"""
        if command[:1] != ("claude",) or "--append-system-prompt-file" in command:
            return command
        self.prepare_agent_area()
        (folder / "guide.md").write_text(self.agent_briefing(task, role), encoding="utf-8", newline="\n")
        where = status.INSIDE if boxed else folder.as_posix()
        return (*command, "--append-system-prompt-file", f"{where}/guide.md")


__all__ = ["AGENT_AREA", "AgentConversations", "AgentModule", "AgentStarted", "CONFIG_KEYS", "CONTAINER_FEATURE",
           "ErrorCode"]
