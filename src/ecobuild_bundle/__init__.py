"""ECOBuild の本体＋同梱の拡張（型 cpp・generic）。CLI はこの層の上にある（この層は CLI を知らない）。

使える型は登録ファイル（module_types.toml）に書いたものだけ。型を指定しなければ cpp。

    from ecobuild_bundle import Module
    module = Module.find(".")
"""

from __future__ import annotations

from importlib import resources

import ecobuild
from ecobuild import tooling as _tooling

REGISTRY_FILE = "module_types.toml"
DEFAULT_TYPE = "cpp"

REGISTRY = ecobuild.Registry.from_toml(
    (resources.files(__name__) / REGISTRY_FILE).read_text(encoding="utf-8"), default=DEFAULT_TYPE)


class Module(ecobuild.Module):
    """同梱の型（REGISTRY）を使う Module。"""
    registry = REGISTRY


def doctor() -> _tooling.DoctorReport:
    return _tooling.doctor(REGISTRY.available())


def setup(**options) -> _tooling.SetupReport:
    return _tooling.setup(REGISTRY.available(), **options)


def initialize(questions: _tooling.Questions) -> _tooling.InitReport:
    return _tooling.initialize(questions, REGISTRY.available())


def config_keys() -> dict[str, str]:
    return _tooling.config_keys(REGISTRY.available())


def set_config(key: str, value: str | None) -> dict[str, str]:
    return _tooling.set_config(key, value, REGISTRY.available())


__all__ = ["DEFAULT_TYPE", "Module", "REGISTRY", "config_keys", "doctor", "initialize", "set_config", "setup"]
