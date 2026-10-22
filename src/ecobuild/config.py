"""モジュールの共有設定（ecobuild.toml）の読み書き。"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path


from .errors import EcoBuildError, ErrorCode, operation

# ECOBuildのファイルの置き場所（モジュールのルートからの相対）。共有の設定・このPC用の設定・ログ（CLI）と、
# 型が使う内部のファイル（cpp：CppBuildの .cppbuild）をここにまとめる。
DIRECTORY = ".ecobuild"
FILE_NAME = f"{DIRECTORY}/ecobuild.toml"
LOCAL_FILE_NAME = f"{DIRECTORY}/ecobuild.local.toml"   # このPC用（.ecobuild/.gitignore で除外）
# モジュールの仕様の版（ecobuild.toml の format）。ECOBuild がモジュールに作るファイル（.gitignore・AGENTS.md 等）
# の中身や置き場所を変えたら1つ上げる。古い版のモジュールは読めて、module upgrade で今の版にする（Module.upgrade）。
# 1：最初の版。2：module upgrade ができた版（中身の変更なし）。3：拡張が置くファイル（Module.environment_files。コンテナの環境 .ecobuild/container/Dockerfile）。
# 4：作業空間が元の clone の中の worktree（.ecobuild/w/）になり、AGENTS.md・.ecobuild/README.md がそれと、ECOBuild が起動したエージェントのツール（MCP）を案内する。
FORMAT = 4


@dataclass(frozen=True)
class Profile:
    """名前付きビルド設定（I-002・I-024）。CppBuildが保存しない設定をECOBuildが保存する。"""
    configuration: str = "Debug"
    shared: bool = False          # ライブラリ（依存先を含む）を共有ライブラリとしてビルド・リンクする
    parallel: int = 1             # 並列ビルドの数
    # 型ごとのビルド設定（cpp：architecture・cpp_standard・generator 等）。本体は中身を知らず、型が確かめて使う
    options: dict[str, str | int | bool] = field(default_factory=dict)
    # Projectごとの上書き（Project名 → 型ごとの設定。cpp：type・cpp_standard 等）
    projects: dict[str, dict[str, str | int | bool]] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectNames:
    """以前のモジュールの [projects]（作成時に作った基本のProject）。今は使わず、読み書きだけ残す。"""
    library: str
    test: str
    app: str | None = None


_KNOWN_TABLES = ("format", "module", "branches", "projects", "profiles")

# CI（ecobuild ci init）で選べるOS → GitHub Actions のランナー
CI_RUNNERS = {"windows": "windows-latest", "linux": "ubuntu-latest"}
CI_TABLE = "ci"
CI_REVIEW_AUTH = ("subscription", "api-key")   # 中身（シークレットの名前等）は ecobuild.ci_review.AUTH
# 以前の設定：タスクの計画を置くボードの接続（今は内部で見つける。url だけ、引き継ぐために読む）
LEGACY_BOARD_TABLE = "board"


@dataclass(frozen=True)
class CiSettings:
    """CIの設定（ecobuild.toml の [ci]）。ワークフローは ecobuild ci init でこの設定から作り直す。"""
    os: tuple[str, ...] | None = None              # None：型の既定（cpp：windows・linux、generic：linux）
    configurations: tuple[str, ...] = ("Debug",)
    shared: bool = False                           # ライブラリを共有ライブラリにした構成でもビルド・テストする
    branches: tuple[str, ...] | None = None        # pushでCIを動かすブランチ。None：default_base（PRでは常に動く）
    review: bool = False                           # 提出（PR）を Claude が見直す（ecobuild.ci_review）
    review_auth: str = "subscription"              # 見直しの認証：subscription（契約のトークン）・api-key


CHECK_TABLE = "check"
# 提出の前に行える確認の項目（ecobuild check の項目のうち、選べるもの）
SUBMIT_CHECK_ITEMS = ("generated", "conflict_markers", "build", "test")


@dataclass(frozen=True)
class SubmitChecks:
    """task submit の前に行う確認（ecobuild.toml の [check]）。既定は何もしない（items が空）。

    提出の確認を全部の試験にすると、提出のたびに長く待つ（ECOBuild 自身で1回20分以上）。何を行うかはモジュールが
    決める（ユーザーの決定「提出時に行う確認をユーザーが設定できるように。既定は何もせずに通過」）。"""
    items: tuple[str, ...] = ()                    # SUBMIT_CHECK_ITEMS のうち行うもの
    tests: tuple[str, ...] = ()                    # test で流す試験（型が絞れるとき。空なら全部）


def validate_submit_checks(settings: SubmitChecks) -> None:
    unknown = [name for name in settings.items if name not in SUBMIT_CHECK_ITEMS]
    if unknown:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"提出の確認の項目 {', '.join(unknown)} はありません。",
                            hint=f"{'・'.join(SUBMIT_CHECK_ITEMS)} から選んでください（カンマ区切り。なしは none）。")
    if settings.tests and "test" not in settings.items:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "流す試験は、提出の確認に test があるときだけ指定できます。")


@dataclass(frozen=True)
class ModuleConfig:
    name: str
    projects: ProjectNames | None = None   # 以前のモジュールの [projects]。新しいモジュールにはない
    type: str = ""                        # モジュールの型（ecobuild.toml には必ずある。本体に既定の型はない）
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
        for key in ("shared", "review"):
            if not isinstance(table.get(key, False), bool):
                raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"[ci] の {key} は真偽値です（true／false）。")
        configurations = _ci_strings(table, "configurations")
        settings = CiSettings(
            os=_ci_strings(table, "os"),
            configurations=("Debug",) if configurations is None else configurations,
            shared=table.get("shared", False),
            branches=_ci_strings(table, "branches"),
            review=table.get("review", False),
            review_auth=table.get("review_auth", "subscription"),
        )
        validate_ci(settings)
        return settings

    @property
    def submit_checks(self) -> SubmitChecks:
        table = self.extra.get(CHECK_TABLE, {})
        settings = SubmitChecks(items=_strings(table, "submit", CHECK_TABLE) or (),
                                tests=_strings(table, "tests", CHECK_TABLE) or ())
        validate_submit_checks(settings)
        return settings

    def with_submit_checks(self, settings: SubmitChecks) -> "ModuleConfig":
        validate_submit_checks(settings)
        extra = {key: value for key, value in self.extra.items() if key != CHECK_TABLE}
        if settings.items or settings.tests:
            extra[CHECK_TABLE] = {"submit": list(settings.items), **({"tests": list(settings.tests)} if settings.tests else {})}
        return replace(self, extra=extra)

    @property
    def legacy_board(self) -> str | None:
        """以前の設定（[board] の url）。なければNone。"""
        url = self.extra.get(LEGACY_BOARD_TABLE, {}).get("url")
        return url if isinstance(url, str) and url else None

    def with_ci(self, settings: CiSettings) -> "ModuleConfig":
        validate_ci(settings)
        table = {"configurations": list(settings.configurations), "shared": settings.shared}
        if settings.os is not None:
            table = {"os": list(settings.os), **table}
        if settings.branches is not None:
            table["branches"] = list(settings.branches)
        if settings.review:
            table["review"] = True
        if settings.review_auth != "subscription":
            table["review_auth"] = settings.review_auth
        return replace(self, extra={**self.extra, CI_TABLE: table})

    @classmethod
    def for_new_module(cls, name: str, type: str) -> "ModuleConfig":
        return cls(name=name, type=type)


def _ci_strings(table: dict, key: str) -> tuple[str, ...] | None:
    """[ci] の文字列の配列（なければNone）。配列でない・文字列でない要素は設定の誤り。"""
    return _strings(table, key, CI_TABLE)


def _strings(table: dict, key: str, name: str) -> tuple[str, ...] | None:
    """[name] の文字列の配列（なければNone）。配列でない・文字列でない要素は設定の誤り。"""
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"[{name}] の {key} は文字列の配列です（例：{key} = [\"...\"]）。")
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
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "CIを動かすブランチを1つ以上指定してください（タスクブランチは除く）。")
    if not isinstance(settings.shared, bool):
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, "[ci] の shared は真偽値です。")
    if settings.review_auth not in CI_REVIEW_AUTH:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"見直しの認証 {settings.review_auth} は使えません。",
                            hint=f"{'・'.join(CI_REVIEW_AUTH)} から選んでください。")


def load(path: Path) -> ModuleConfig:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        version = data.get("format")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError("format は1以上の整数です")
        if version > FORMAT:
            raise EcoBuildError(ErrorCode.INVALID_CONFIG,
                                f"このモジュールは新しい ECOBuild の仕様（版 {version}）です。この ECOBuild は版 {FORMAT} までです。",
                                hint="ECOBuild を新しくしてください（インストーラーをもう一度実行）。")
        module = data["module"]
        projects = data.get("projects")
        config = ModuleConfig(
            name=_text(module, "name"),
            type=_text(module, "type"),  # 型があるかは本体が登録ファイルで確かめる
            default_base=_text(data.get("branches", {"default_base": "main"}), "default_base"),
            format=version,
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
        lines += [f"{key} = {_value(value)}" for key, value in sorted(profile.options.items())]
        for project, values in sorted(profile.projects.items()):
            lines += ["", f"[profiles.{_quote(name)}.projects.{_quote(project)}]"]
            lines += [f"{key} = {_value(value)}" for key, value in sorted(values.items())]
    return "\n".join(lines) + "\n"


def save(config: ModuleConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(config), encoding="utf-8", newline="\n")


def find_root(start: Path, *, command: str = "") -> Path:
    """startから上へecobuild.tomlを探し、最も近いものがあるディレクトリを返す。command：ヒントに書くプログラム名。"""
    current = start.resolve()
    for directory in (current, *current.parents):
        if (directory / FILE_NAME).is_file():
            return directory
    raise EcoBuildError(
        ErrorCode.NOT_IN_MODULE,
        f"{start} はECOBuildのモジュールの中ではありません（{FILE_NAME} が見つかりません）。",
        hint=f"モジュールのディレクトリへ移動するか、{operation(command, 'module new')} <名前> で作成してください"
             f"（既にある GitHub のリポジトリの clone なら {operation(command, 'module adopt')}）。",
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
    (root / DIRECTORY).mkdir(parents=True, exist_ok=True)
    (root / LOCAL_FILE_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _profile(name: str, table: dict) -> Profile:
    projects = table.get("projects", {})
    if not isinstance(projects, dict) or not all(isinstance(v, dict) for v in projects.values()):
        raise ValueError(f"profiles.{name}.projects は Project名 → 表 です")
    options = {k: v for k, v in table.items() if k not in ("configuration", "shared", "parallel", "projects")}
    for key, value in [*options.items(), *(item for values in projects.values() for item in values.items())]:
        if not isinstance(value, (str, int, bool)):
            raise ValueError(f"profiles.{name} の {key} は文字列・整数・真偽値です")
    profile = Profile(
        configuration=table.get("configuration", "Debug"),
        shared=table.get("shared", False),
        parallel=table.get("parallel", 1),
        options=options,
        projects={project: dict(values) for project, values in projects.items()},
    )
    if not isinstance(profile.configuration, str) or not profile.configuration:
        raise ValueError(f"profiles.{name}.configuration は空でない文字列です")  # 値の確認は型が行う
    if not isinstance(profile.shared, bool) or not isinstance(profile.parallel, int) or profile.parallel < 1:
        raise ValueError(f"profiles.{name} の shared は真偽値、parallel は1以上の整数です")
    return profile


def _simple_table(name: str, value: object) -> dict:
    """型ごとの表。値は文字列・整数・真偽値・文字列の並び・文字列の表（{ windows = "..." } 等）だけ
    （そのまま書き戻せる形）。"""
    if not isinstance(value, dict) or not all(_value_ok(v) for v in value.values()):
        raise ValueError(f"[{name}] の値は文字列・整数・真偽値・文字列の並び・文字列の表にしてください")
    return dict(value)


def _value_ok(value: object) -> bool:
    return isinstance(value, (str, int, bool)) or (isinstance(value, list) and all(isinstance(v, str) for v in value)) \
        or (isinstance(value, dict) and all(isinstance(v, str) for v in value.values()))


def _value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(_quote(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_quote(k)} = {_quote(v)}" for k, v in value.items()) + " }"
    return str(value) if isinstance(value, int) else _quote(value)


def _text(table: dict, key: str) -> str:
    value = table[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} は空でない文字列である必要があります")
    return value


def _quote(value: str) -> str:
    # TOMLの基本文字列はJSONの文字列と同じエスケープで書ける。
    return json.dumps(value, ensure_ascii=False)
