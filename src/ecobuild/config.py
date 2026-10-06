"""モジュールの共有設定（ecobuild.toml）の読み書き。"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

from .errors import EcoBuildError, ErrorCode

FILE_NAME = "ecobuild.toml"
LOCAL_FILE_NAME = "ecobuild.local.toml"   # このPC用（.gitignore対象）
FORMAT = 1
DEPENDENCY_DIRECTORY = "deps"
CONFIGURATIONS = ("Debug", "Release", "RelWithDebInfo", "MinSizeRel")


@dataclass(frozen=True)
class Profile:
    """名前付きビルド設定（I-002・I-024）。CppBuildが保存しない設定をECOBuildが保存する。"""
    configuration: str = "Debug"
    shared: bool = False          # ライブラリ（依存先を含む）を共有ライブラリとしてビルド・リンクする
    parallel: int = 1             # 並列ビルドの数


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
    profiles: dict[str, Profile] = field(default_factory=dict)

    def with_profiles(self, profiles: dict[str, Profile]) -> "ModuleConfig":
        return replace(self, profiles=dict(sorted(profiles.items())))

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
            profiles={name: _profile(name, table) for name, table in data.get("profiles", {}).items()},
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
        "# task start の --base を省略したときの作成元",
        f"default_base = {_quote(config.default_base)}",
        "",
        "[projects]",
        f"library = {_quote(config.projects.library)}",
        f"test = {_quote(config.projects.test)}",
    ]
    if config.projects.app is not None:
        lines.append(f"app = {_quote(config.projects.app)}")
    if config.profiles:
        lines += ["", "# 名前付きビルド設定（ecobuild profile）。選択は ecobuild.local.toml（このPC用）"]
    for name, profile in config.profiles.items():
        lines += [
            "",
            f"[profiles.{_quote(name)}]",
            f"configuration = {_quote(profile.configuration)}",
            f"shared = {'true' if profile.shared else 'false'}",
            f"parallel = {profile.parallel}",
        ]
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


def load_local(root: Path) -> dict:
    """このPC用の設定（ecobuild.local.toml）。なければ空。"""
    path = root / LOCAL_FILE_NAME
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"{path} を読み込めません：{error}") from error


def save_local(root: Path, values: dict) -> None:
    lines = ["# ECOBuildのこのPC用の設定（コミットしない）。"]
    lines += [f"{key} = {_quote(value)}" for key, value in sorted(values.items()) if value is not None]
    (root / LOCAL_FILE_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _profile(name: str, table: dict) -> Profile:
    profile = Profile(
        configuration=table.get("configuration", "Debug"),
        shared=table.get("shared", False),
        parallel=table.get("parallel", 1),
    )
    if profile.configuration not in CONFIGURATIONS:
        raise ValueError(f"profiles.{name}.configuration は {'・'.join(CONFIGURATIONS)} のどれかです")
    if not isinstance(profile.shared, bool) or not isinstance(profile.parallel, int) or profile.parallel < 1:
        raise ValueError(f"profiles.{name} の shared は真偽値、parallel は1以上の整数です")
    return profile


def _text(table: dict, key: str) -> str:
    value = table[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} は空でない文字列である必要があります")
    return value


def _quote(value: str) -> str:
    # TOMLの基本文字列はJSONの文字列と同じエスケープで書ける。
    return json.dumps(value, ensure_ascii=False)
