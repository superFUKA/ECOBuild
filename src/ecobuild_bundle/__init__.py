"""ECOBuild の本体＋同梱の拡張（型 cpp・generic）。CLI はこの層の上にある（この層は CLI を知らない）。

使える型は登録ファイル（module_types.toml）に書いたものだけ。型を指定しなければ cpp。
このPCの準備（doctor・setup・init）も、同梱の型が使うツールを含めてここで行う（tooling）。

    from ecobuild_bundle import Module
    module = Module.find(".")
"""

from __future__ import annotations

import sys
from importlib import resources
from pathlib import Path
from typing import Iterable

import ecoagent
import ecobuild
from ecobuild import config as _config
from ecobuild import settings as _settings
from ecobuild import workspaces as _workspaces
from ecobuild.errors import WorkError
from ecobuild.results import AgentConversations, AgentStarted, DoctorItem

from . import team, tooling

AGENT_AREA = ".ecobuild/ai"   # 作業空間の中のエージェント用の置き場所（コミットしない。prepare_agent_area）
REGISTRY_FILE = "module_types.toml"
DEFAULT_TYPE = "cpp"

REGISTRY = ecobuild.Registry.from_toml(
    (resources.files(__name__) / REGISTRY_FILE).read_text(encoding="utf-8"), default=DEFAULT_TYPE)


class Module(ecobuild.Module):
    """同梱の型（REGISTRY）を使う Module。"""
    registry = REGISTRY

    @classmethod
    def close_workspace(cls, path, **options):
        """閉じたら、その作業空間のコンテナも消す（Docker が使えなければそのまま。中のものは作業空間にない）。"""
        from . import container
        try:   # 閉じると ecobuild.local.toml も消えるので、先に読む
            chosen = container.enabled(_workspaces.module_root(Path(path)))
        except WorkError:
            chosen = False
        closed = super().close_workspace(path, **options)
        if closed.done and chosen:
            container.discard(closed.path)
        return closed

    def start_agent(self, command=ecoagent.DEFAULT_COMMAND, *, source=None,
                    progress=lambda message: None, role: str = "", prompt: str = "") -> AgentStarted:
        """コンテナにした作業空間では、コンテナの中で確認なしに起動する（使わせないものは設定 agent_deny）。
        source：コンテナのイメージに入れる ECOBuild（container.start と同じ）。Claude Code には、ECOBuild の使い方
        （agent_briefing）を最初から渡す。role：進行役（lead）か作業役（worker。既定は作業空間の記録、なければ作業役）。
        prompt：最初の発言。"""
        from . import agent_status, container
        inside = container.enabled(self.root)
        task = self.require_task_branch("エージェントの起動")
        role = team.role_of(self.root, role)
        command = self._for_role(tuple(command), role, prompt)
        command = self._briefed(command, agent_status.prepare(container.name(self.root), self.root), inside, task, role)
        if not inside:
            return super().start_agent(command)
        session = container.start_agent(self.root, command, deny=self._agent_deny(), command=self.command,
                                        source=source, progress=progress)
        return AgentStarted(session.pid, session.command, session.directory)

    def run_agent(self, command=ecoagent.DEFAULT_COMMAND, *, source=None, progress=lambda message: None,
                  role: str = "", prompt: str = "") -> int:
        """この端末で動かして待つ（start_agent と同じく、コンテナならその中で）。Claude Code なら、状態（モデル・
        使用量・返答の終わり）を書き出させ、その置き場所を端末に知らせる（agent_status。画面を持つアプリが読む）。"""
        from . import agent_status, container
        inside = container.enabled(self.root)
        task = self.require_task_branch("エージェントの起動")
        role = team.role_of(self.root, role)
        command = self._for_role(tuple(command), role, prompt)
        if command[:1] == ("claude",):
            folder = agent_status.prepare(container.name(self.root), self.root)
            agent_status.announce(folder)
            where, python = (agent_status.INSIDE, "python3") if inside else (folder.as_posix(), agent_status.host_python())
            command = (*command, "--settings", agent_status.settings_argument(folder, where, python))
            command = self._briefed(command, folder, inside, task, role)
        if not inside:
            return super().run_agent(command)
        return container.start_agent(self.root, command, deny=self._agent_deny(), command=self.command,
                                     source=source, progress=progress, here=True)

    def agent_conversations(self, limit: int = 20):
        """コンテナにした作業空間では、中の会話（すべてのコンテナで共有する設定の場所にある。中の場所はどれも同じ
        なので、今のブランチでの会話だけ）。コンテナが動いていなければ読まない（note にわけ）。"""
        from . import container
        if not container.enabled(self.root):
            return super().agent_conversations(limit)
        found, note = container.agent_conversations(self.root, self.repository.git.current_branch() or "", limit,
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
        import subprocess
        area = self.root / AGENT_AREA
        area.mkdir(parents=True, exist_ok=True)
        try:
            found = subprocess.run(["git", "-C", str(self.root), "rev-parse", "--git-path", "info/exclude"],
                                   capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return area
        if found.returncode == 0 and found.stdout.strip():
            exclude = Path(found.stdout.strip())
            exclude = exclude if exclude.is_absolute() else self.root / exclude
            line = f"/{AGENT_AREA}/"
            text = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
            if line not in text.splitlines():
                exclude.parent.mkdir(parents=True, exist_ok=True)
                exclude.write_text(text + ("" if not text or text.endswith("\n") else "\n")
                                   + f"# ECOBuild：エージェント用の置き場所（コミットしない）\n{line}\n", encoding="utf-8")
        return area

    def _for_role(self, command: tuple[str, ...], role: str, prompt: str) -> tuple[str, ...]:
        """役のモデル・使わせない道具（team.agent_options）と、最初の発言（claude のすぐ後ろ：--disallowedTools 等の
        いくつも値を取る引数の後ろに置くと、その値として読まれる）。"""
        command = team.agent_options(self.root, role, command)
        return (command[0], prompt, *command[1:]) if prompt.strip() and command[:1] == ("claude",) else command

    def _briefed(self, command: tuple[str, ...], folder: Path, inside: bool, task,
                 role: str = team.WORKER) -> tuple[str, ...]:
        """Claude Code なら、使い方の文をファイル（状態の置き場所の guide.md）にして --append-system-prompt-file で渡す
        （長い文を引数にしない：claude.cmd は cmd.exe を通る）。"""
        from . import agent_status
        if command[:1] != ("claude",) or "--append-system-prompt-file" in command:
            return command
        self.prepare_agent_area()
        (folder / "guide.md").write_text(self.agent_briefing(task, role), encoding="utf-8", newline="\n")
        where = agent_status.INSIDE if inside else folder.as_posix()
        return (*command, "--append-system-prompt-file", f"{where}/guide.md")

    def _agent_deny(self) -> tuple[str, ...]:
        from . import container
        local = container.split_rules(_config.load_local(self.root).get(container.DENY_KEY) or "")
        return (*container.split_rules(_settings.load_config().get("agent_deny", "")), *local)


def doctor(extra: Iterable[DoctorItem] = (), *, command: str = "") -> tooling.DoctorReport:
    return tooling.doctor(REGISTRY.available(), extra, command=command)


def setup(**options) -> tooling.SetupReport:
    return tooling.setup(REGISTRY.available(), **options)


def initialize(questions: tooling.Questions, extra: Iterable[DoctorItem] = (), *,
               command: str = "") -> tooling.InitReport:
    return tooling.initialize(questions, REGISTRY.available(), extra, command=command)


def config_keys() -> dict[str, str]:
    return _settings.config_keys(REGISTRY.available())


def set_config(key: str, value: str | None) -> dict[str, str]:
    return _settings.set_config(key, value, REGISTRY.available())


__all__ = ["DEFAULT_TYPE", "Module", "REGISTRY", "config_keys", "doctor", "initialize", "set_config", "setup", "tooling"]
