"""ECOBuild の本体＋同梱の拡張（Composition Root）。CLI はこの層の上にある（この層は CLI を知らない）。

つなぐだけ：型（cpp・generic・python。登録ファイル module_types.toml）と、作業空間に付ける環境の拡張（コンテナ
ecobuild_container・エージェント ecobuild_agent）を本体に重ねる。型を指定しなければ cpp。
このPCの準備（doctor・setup・init）も、同梱の型・拡張が使うツールを含めてここで行う（tooling）。

    from ecobuild_bundle import Module
    module = Module.find(".")
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Iterable

import ecobuild
import ecobuild_agent
import ecobuild_container
from ecobuild import config as _config
from ecobuild import locks as _locks
from ecobuild import settings as _settings
from ecobuild.errors import EcoBuildError
from ecobuild.results import DoctorItem

from . import tooling

REGISTRY_FILE = "module_types.toml"
DEFAULT_TYPE = "cpp"

REGISTRY = ecobuild.Registry.from_toml(
    (resources.files(__name__) / REGISTRY_FILE).read_text(encoding="utf-8"), default=DEFAULT_TYPE)

# コンテナの拡張に、型の一覧と、エージェントがコンテナに足すもの（Claude Code 等）を渡す
ecobuild_container.use(REGISTRY, (ecobuild_agent.CONTAINER_FEATURE,))

# 作業空間のロック（使用中）の理由のうち、拡張が知っているもの：エージェントが動いている間・コンテナが動いている間
_locks.add_source(ecobuild_agent.lock_source)
_locks.add_source(ecobuild_container.lock_source)

CONFIG_KEYS = {**ecobuild_agent.CONFIG_KEYS}   # 拡張が名乗る、このPCの設定の項目


class Module(ecobuild_agent.AgentModule, ecobuild_container.ContainerModule, ecobuild.Module):
    """同梱の型（REGISTRY）と、作業空間の環境の拡張（エージェント・コンテナ）を重ねた Module。"""
    registry = REGISTRY


def doctor(extra: Iterable[DoctorItem] = (), *, command: str = "", path: Path | str = ".") -> tooling.DoctorReport:
    """このPCの診断。path がモジュールの中なら、型のツールはそのモジュールの型の分だけを必須にする。"""
    return tooling.doctor(REGISTRY.available(), extra, command=command, module_type=_module_type_at(Path(path)))


def _module_type_at(path: Path) -> str | None:
    """path を含むモジュールの型（モジュールの外・設定が読めなければ None）。"""
    try:
        return _config.load(_config.find_root(path) / _config.FILE_NAME).type or None
    except (EcoBuildError, OSError):
        return None


def setup(**options) -> tooling.SetupReport:
    return tooling.setup(REGISTRY.available(), **options)


def initialize(questions: tooling.Questions, extra: Iterable[DoctorItem] = (), *,
               command: str = "") -> tooling.InitReport:
    return tooling.initialize(questions, REGISTRY.available(), extra, command=command)


def config_keys() -> dict[str, str]:
    return _settings.config_keys(REGISTRY.available(), CONFIG_KEYS)


def set_config(key: str, value: str | None) -> dict[str, str]:
    return _settings.set_config(key, value, REGISTRY.available(), CONFIG_KEYS)


__all__ = ["CONFIG_KEYS", "DEFAULT_TYPE", "Module", "REGISTRY", "config_keys", "doctor", "initialize", "set_config",
           "setup", "tooling"]
