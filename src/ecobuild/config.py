"""モジュールの共有設定（ecobuild.toml）の読み書き。"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import EcoBuildError, ErrorCode

FILE_NAME = "ecobuild.toml"
FORMAT = 1
DEPENDENCY_DIRECTORY = "deps"


@dataclass(frozen=True)
class ProjectNames:
    library: str
    test: str
    app: str | None = None


@dataclass(frozen=True)
class ModuleConfig:
    name: str
    projects: ProjectNames
    type: str = "cpp"
    default_base: str = "main"
    format: int = FORMAT

    @classmethod
    def for_new_module(cls, name: str, *, app: bool) -> "ModuleConfig":
        return cls(name=name, projects=ProjectNames(name, name + "Test", name + "App" if app else None))


def load(path: Path) -> ModuleConfig:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != FORMAT:
            raise ValueError(f"format は {FORMAT} である必要があります")
        module = data["module"]
        projects = data["projects"]
        config = ModuleConfig(
            name=_text(module, "name"),
            type=_text(module, "type"),
            default_base=_text(data.get("branches", {"default_base": "main"}), "default_base"),
            projects=ProjectNames(
                library=_text(projects, "library"),
                test=_text(projects, "test"),
                app=_text(projects, "app") if "app" in projects else None,
            ),
        )
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as error:
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"{path} を読み込めません：{error}") from error
    if config.type != "cpp":
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"{path}：型 {config.type!r} には対応していません。")
    return config


def dump(config: ModuleConfig) -> str:
    lines = [
        "# ECOBuildのモジュール設定。",
        f"format = {config.format}",
        "",
        "[module]",
        f"name = {_quote(config.name)}",
        f"type = {_quote(config.type)}",
        "",
        "[branches]",
        "# task start の --from を省略したときの作成元",
        f"default_base = {_quote(config.default_base)}",
        "",
        "[projects]",
        f"library = {_quote(config.projects.library)}",
        f"test = {_quote(config.projects.test)}",
    ]
    if config.projects.app is not None:
        lines.append(f"app = {_quote(config.projects.app)}")
    return "\n".join(lines) + "\n"


def save(config: ModuleConfig, path: Path) -> None:
    path.write_text(dump(config), encoding="utf-8", newline="\n")


def find_root(start: Path) -> Path:
    """startから上へecobuild.tomlを探し、最も近いものがあるディレクトリを返す。"""
    current = start.resolve()
    for directory in (current, *current.parents):
        if (directory / FILE_NAME).is_file():
            return directory
    raise EcoBuildError(
        ErrorCode.NOT_IN_MODULE,
        f"{start} はECOBuildのモジュールの中ではありません（{FILE_NAME} が見つかりません）。",
        hint="モジュールのディレクトリへ移動するか、ecobuild new <名前> で作成してください。",
    )


def _text(table: dict, key: str) -> str:
    value = table[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} は空でない文字列である必要があります")
    return value


def _quote(value: str) -> str:
    # TOMLの基本文字列はJSONの文字列と同じエスケープで書ける。
    return json.dumps(value, ensure_ascii=False)
