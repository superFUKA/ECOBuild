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
from ecobuild.results import AgentStarted, DoctorItem

from . import tooling

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
                    progress=lambda message: None) -> AgentStarted:
        """コンテナにした作業空間では、コンテナの中で確認なしに起動する（使わせないものは設定 agent_deny）。
        source：コンテナのイメージに入れる ECOBuild（container.start と同じ）。"""
        from . import container
        if not container.enabled(self.root):
            return super().start_agent(command)
        self.require_task_branch("エージェントの起動")
        session = container.start_agent(self.root, tuple(command), deny=self._agent_deny(), command=self.command,
                                        source=source, progress=progress)
        return AgentStarted(session.pid, session.command, session.directory)

    def run_agent(self, command=ecoagent.DEFAULT_COMMAND, *, source=None, progress=lambda message: None) -> int:
        """この端末で動かして待つ（start_agent と同じく、コンテナならその中で）。Claude Code なら、状態（モデル・
        使用量・返答の終わり）を書き出させ、その置き場所を端末に知らせる（agent_status。画面を持つアプリが読む）。"""
        from . import agent_status, container
        inside = container.enabled(self.root)
        self.require_task_branch("エージェントの起動")
        command = tuple(command)
        if command[:1] == ("claude",):
            folder = agent_status.prepare(container.name(self.root))
            agent_status.announce(folder)
            where, python = (agent_status.INSIDE, "python3") if inside else (folder.as_posix(), f'"{Path(sys.executable).as_posix()}"')
            command = (*command, "--settings", agent_status.claude_settings(where, python))
        if not inside:
            return super().run_agent(command)
        return container.start_agent(self.root, command, deny=self._agent_deny(), command=self.command,
                                     source=source, progress=progress, here=True)

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
