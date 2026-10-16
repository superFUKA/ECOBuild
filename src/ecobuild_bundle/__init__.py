"""ECOBuild の本体＋同梱の拡張（型 cpp・generic）。CLI はこの層の上にある（この層は CLI を知らない）。

使える型は登録ファイル（module_types.toml）に書いたものだけ。型を指定しなければ cpp。
このPCの準備（doctor・setup・init）も、同梱の型が使うツールを含めてここで行う（tooling）。

    from ecobuild_bundle import Module
    module = Module.find(".")
"""

from __future__ import annotations

from importlib import resources
from typing import Iterable

import ecobuild
from ecobuild import settings as _settings
from ecobuild.results import DoctorItem

from . import tooling

REGISTRY_FILE = "module_types.toml"
DEFAULT_TYPE = "cpp"

REGISTRY = ecobuild.Registry.from_toml(
    (resources.files(__name__) / REGISTRY_FILE).read_text(encoding="utf-8"), default=DEFAULT_TYPE)


class Module(ecobuild.Module):
    """同梱の型（REGISTRY）を使う Module。"""
    registry = REGISTRY


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
