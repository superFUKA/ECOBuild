"""モジュールの共有設定（ecobuild.toml）の読み書き。"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

from ecotask.board import BoardSettings

from .errors import EcoBuildError, ErrorCode

FILE_NAME = "ecobuild.toml"
LOCAL_FILE_NAME = "ecobuild.local.toml"   # このPC用（.gitignore対象）
FORMAT = 1


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


_KNOWN_TABLES = ("format", "module", "branches", "projects", "profiles")

# CI（ecobuild ci init）で選べるOS → GitHub Actions のランナー
CI_RUNNERS = {"windows": "windows-latest", "linux": "ubuntu-latest"}
CI_TABLE = "ci"
BOARD_TABLE = "board"
BOARD_STAGES = ("todo", "in_progress", "in_review", "done")   # 作業の段階（ecowork.board と同じ）


@dataclass(frozen=True)
class CiSettings:
    """CIの設定（ecobuild.toml の [ci]）。ワークフローは ecobuild ci init でこの設定から作り直す。"""
    os: tuple[str, ...] | None = None              # None：型の既定（cpp：windows・linux、generic：linux）
    configurations: tuple[str, ...] = ("Debug",)
    shared: bool = False                           # ライブラリを共有ライブラリにした構成でもビルド・テストする
    branches: tuple[str, ...] | None = None        # pushでCIを動かすブランチ。None：default_base（PRでは常に動く）


@dataclass(frozen=True)
class ModuleConfig:
    name: str
    projects: ProjectNames | None      # 基本のProject（型が使わなければNone）
    type: str = "cpp"
    default_base: str = "main"
    format: int = FORMAT
    profiles: dict[str, Profile] = field(default_factory=dict)
    # 型ごとの表（例：generic 型の [commands]）。本体は中身を知らず、そのまま読み書きする
    extra: dict[str, dict] = field(default_factory=dict)

    def with_profiles(self, profiles: dict[str, Profile]) -> "ModuleConfig":
        return replace(self, profiles=dict(sorted(profiles.items())))

    @property
    def ci(self) -> CiSettings:
        table = self.extra.get(CI_TABLE, {})
        if not isinstance(table.get("shared", False), bool):
            raise EcoBuildError(ErrorCode.INVALID_CONFIG, "[ci] の shared は真偽値です（true／false）。")
        configurations = _ci_strings(table, "configurations")
        settings = CiSettings(
            os=_ci_strings(table, "os"),
            configurations=("Debug",) if configurations is None else configurations,
            shared=table.get("shared", False),
            branches=_ci_strings(table, "branches"),
        )
        validate_ci(settings)
        return settings

    @property
    def board(self) -> BoardSettings | None:
        """タスクの計画を置くボード（[board]）。なければNone。"""
        table = self.extra.get(BOARD_TABLE)
        if table is None:
            return None
        url, status = table.get("url"), table.get("status_field", "Status")
        stages = {stage: table[stage] for stage in BOARD_STAGES if table.get(stage)}
        if not isinstance(url, str) or not isinstance(status, str) or not all(isinstance(v, str) for v in stages.values()):
            raise EcoBuildError(ErrorCode.INVALID_CONFIG, "[board] の url・status_field・段階の選択肢は文字列です。")
        return BoardSettings(url, status, stages)

    def with_board(self, settings: BoardSettings | None) -> "ModuleConfig":
        extra = {k: v for k, v in self.extra.items() if k != BOARD_TABLE}
        if settings is not None:
            extra[BOARD_TABLE] = {"url": settings.url, "status_field": settings.status_field,
                                  **{stage: settings.stages[stage] for stage in BOARD_STAGES if settings.stages.get(stage)}}
        return replace(self, extra=extra)

    def with_ci(self, settings: CiSettings) -> "ModuleConfig":
        validate_ci(settings)
        table = {"configurations": list(settings.configurations), "shared": settings.shared}
        if settings.os is not None:
            table = {"os": list(settings.os), **table}
        if settings.branches is not None:
            table["branches"] = list(settings.branches)
        return replace(self, extra={**self.extra, CI_TABLE: table})

    @classmethod
    def for_new_module(cls, name: str, *, app: bool) -> "ModuleConfig":
        return cls(name=name, projects=ProjectNames(name, name + "Test", name + "App" if app else None))


def _ci_strings(table: dict, key: str) -> tuple[str, ...] | None:
    """[ci] の文字列の配列（なければNone）。配列でない・文字列でない要素は設定の誤り。"""
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"[ci] の {key} は文字列の配列です（例：{key} = [\"...\"]）。")
    return tuple(value)


def validate_ci(settings: CiSettings) -> None:
    unknown = [name for name in settings.os or () if name not in CI_RUNNERS]
    if unknown or settings.os == ():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"CIのOS {', '.join(unknown) or '（空）'} は使えません。",
                            hint=f"{'・'.join(CI_RUNNERS)} から選んでください（カンマ区切り）。")
    if not settings.configurations or not all(isinstance(c, str) and c for c in settings.configurations):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "CIの構成を1つ以上指定してください（例：Debug,Release）。")
    if settings.branches is not None and (not settings.branches or not all(
            isinstance(b, str) and b and not b.startswith("task/") for b in settings.branches)):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "CIを動かすブランチを1つ以上指定してください（作業空間は除く）。")
    if not isinstance(settings.shared, bool):
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, "[ci] の shared は真偽値です。")


def load(path: Path) -> ModuleConfig:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != FORMAT:
            raise ValueError(f"format は {FORMAT} である必要があります")
        module = data["module"]
        projects = data.get("projects")
        config = ModuleConfig(
            name=_text(module, "name"),
            type=_text(module, "type"),  # 型があるかは本体が登録ファイルで確かめる
            default_base=_text(data.get("branches", {"default_base": "main"}), "default_base"),
            projects=None if projects is None else ProjectNames(
                library=_text(projects, "library"),
                test=_text(projects, "test"),
                app=_text(projects, "app") if "app" in projects else None,
            ),
            profiles={name: _profile(name, table) for name, table in data.get("profiles", {}).items()},
            extra={key: _simple_table(key, value) for key, value in data.items() if key not in _KNOWN_TABLES},
        )
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as error:
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"{path} を読み込めません：{error}") from error
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
    ]
    if config.projects is not None:
        lines += ["", "[projects]",
                  f"library = {_quote(config.projects.library)}",
                  f"test = {_quote(config.projects.test)}"]
        if config.projects.app is not None:
            lines.append(f"app = {_quote(config.projects.app)}")
    for table, values in config.extra.items():
        lines += ["", f"[{table}]"] + [f"{key} = {_value(value)}" for key, value in values.items()]
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
    if not isinstance(profile.configuration, str) or not profile.configuration:
        raise ValueError(f"profiles.{name}.configuration は空でない文字列です")  # 値の確認は型が行う
    if not isinstance(profile.shared, bool) or not isinstance(profile.parallel, int) or profile.parallel < 1:
        raise ValueError(f"profiles.{name} の shared は真偽値、parallel は1以上の整数です")
    return profile


def _simple_table(name: str, value: object) -> dict:
    """型ごとの表。値は文字列・整数・真偽値・文字列の並びだけ（そのまま書き戻せる形）。"""
    if not isinstance(value, dict) or not all(_value_ok(v) for v in value.values()):
        raise ValueError(f"[{name}] の値は文字列・整数・真偽値・文字列の並びにしてください")
    return dict(value)


def _value_ok(value: object) -> bool:
    return isinstance(value, (str, int, bool)) or (isinstance(value, list) and all(isinstance(v, str) for v in value))


def _value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(_quote(v) for v in value) + "]"
    return str(value) if isinstance(value, int) else _quote(value)


def _text(table: dict, key: str) -> str:
    value = table[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} は空でない文字列である必要があります")
    return value


def _quote(value: str) -> str:
    # TOMLの基本文字列はJSONの文字列と同じエスケープで書ける。
    return json.dumps(value, ensure_ascii=False)
