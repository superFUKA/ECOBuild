"""型ごとのコマンド：今いるモジュールの型のコマンド（ecobuild_<型>.cli）を、共通のコマンドに重ねる。

- 型のコマンドは、型の実装のパッケージ（登録ファイルの module）の下の cli パッケージに置く（なければ型のコマンドはない）。
  共通のコマンドと同じディレクトリ構造で書く（cli/file/add.py → ecobuild file add）。共通と同じ名前は置けない。
- どの型を重ねるかは、起動したときの今いるディレクトリ（-C の後）のモジュールの ecobuild.toml の型で決める。
  モジュールの外・ecobuild.toml を読めないときは重ねない。
- ほかの型のコマンド（今のモジュールにないもの）を打ったときは、引数の誤りではなく not_supported で止める
  （モジュールの外なら not_in_module 等、モジュールが見つからない本当の理由で止める）。
"""

from __future__ import annotations

import importlib
import types
from pathlib import Path

import click

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_bundle import REGISTRY

from . import _log, commands
from ._output import run_command

PACKAGE = "cli"           # 型の実装のパッケージの下の、型のコマンドのパッケージ名


_reason: str | None = None    # 型が決まらなかった理由（ログ用）


def current(cwd: Path) -> str | None:
    """cwd のモジュールの型の名前。モジュールの外・ecobuild.toml を読めないときは None。

    型の実装は読み込まない（起動のたびに呼ぶため。名前は ecobuild.toml を読むだけで分かる）。
    """
    global _reason
    from ecobuild import config
    try:
        root = config.find_root(cwd)
        _reason = None
        return config.load(root / config.FILE_NAME).type or None
    except Exception as error:   # モジュールの外・壊れた ecobuild.toml：型のコマンドを出さない（理由は使うときに出る）
        _reason = str(error)
        return None


def package(name: str | None) -> types.ModuleType | None:
    """型 name のコマンドのパッケージ（ecobuild_<型>.cli）。型が登録されていない・コマンドがなければ None。"""
    entry = REGISTRY.entries().get(name or "")
    if entry is None:
        return None
    try:
        return importlib.import_module(f"{entry.module}.{PACKAGE}")
    except ModuleNotFoundError as error:
        if error.name not in (f"{entry.module}.{PACKAGE}", entry.module):
            raise
        return None


def extensions(name: str | None) -> list[tuple[str, types.ModuleType]]:
    """CLIFrameWork の create_cli に渡す、重ねるパッケージ。"""
    found = package(name)
    _log.logger.debug("型のコマンド：%s", found.__name__ if found else "なし", extra={"event": "command.type", "data": {
        "type": name, "package": found.__name__ if found else None, "reason": None if name else _reason}})
    return [("", found)] if found is not None else []


def routes(package_: types.ModuleType) -> set[tuple[str, ...]]:
    """パッケージが定義するコマンド・グループの道筋（("project",)・("project", "add") 等）。import せずに調べる。

    _ で始まるファイル・ディレクトリ（共通の部分）と、説明だけの __init__.py は数えない。
    """
    found: set[tuple[str, ...]] = set()
    for directory in map(Path, package_.__path__):
        for path in directory.rglob("*.py"):
            relative = path.relative_to(directory)
            if relative.name == "__init__.py":
                continue
            parts = (*relative.parent.parts, relative.stem)
            if any(part.startswith("_") for part in parts):
                continue
            found.update(parts[:index] for index in range(1, len(parts) + 1))
    return found


def all_routes() -> dict[str, set[tuple[str, ...]]]:
    """登録した型ごとの、型のコマンドの道筋。"""
    result = {}
    for name in REGISTRY.entries():
        found = package(name)
        if found is not None:
            result[name] = routes(found)
    return result


def attach(cli: click.Group, name: str | None) -> None:
    """組み立てた CLI に、型のコマンドの見出し（ecobuild --help）と、ほかの型のコマンドの案内を付ける。"""
    found = package(name)
    own = {route[0] for route in routes(found)} if found is not None else set()
    typed = own - {route[0] for route in routes(commands)}     # 型だけにあるもの（共通のグループに足したものは除く）
    common = [n for n in cli.list_commands(click.Context(cli)) if n not in typed]
    cli.format_commands = types.MethodType(_root_help(common, sorted(typed), name), cli)
    _guard(cli, ())


def _root_help(common: list[str], typed: list[str], name: str | None):
    def format_commands(self, ctx, formatter):
        for title, names in (("コマンド", common), (f"型 {name} のコマンド", typed)):
            rows = []
            for command_name in names:
                command = self.get_command(ctx, command_name)
                if command is not None and not command.hidden:
                    rows.append((command_name, command.get_short_help_str(limit=formatter.width)))
            if rows:
                with formatter.section(title):
                    formatter.write_dl(rows)
        if name is None:
            with formatter.section("型ごとのコマンド"):
                formatter.write_text("build・test・file 等、モジュールの型ごとのコマンドは、モジュールの中で "
                                     "ecobuild --help を実行すると出ます（型の一覧：ecobuild module types）。")

    return format_commands


def _guard(group: click.Group, path: tuple[str, ...]) -> None:
    """group とその下のグループで、ない名前がほかの型のコマンドなら、案内して止めるコマンドを返す。"""
    original = group.get_command

    def get_command(self, ctx, command_name):
        command = original(ctx, command_name)
        if command is not None:
            return command
        route = (*path, command_name)
        owners = [type_name for type_name, found in all_routes().items() if route in found]
        return _Unavailable(route, owners) if owners else None

    group.get_command = types.MethodType(get_command, group)
    for child_name, child in group.commands.items():
        if isinstance(child, click.Group):
            _guard(child, (*path, child_name))


class _Unavailable(click.Command):
    """今のモジュールにない、ほかの型のコマンド。引数は読まずに、理由を出して止める（--json なら JSON で）。"""

    def __init__(self, route: tuple[str, ...], owners: list[str]):
        super().__init__(route[-1], hidden=True, add_help_option=False,
                         context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
        self.route = route
        self.owners = owners

    def invoke(self, ctx: click.Context):
        command = " ".join(self.route)

        def action(inv):
            module = inv.module      # モジュールの外・ecobuild.toml を読めない・型が登録されていない：その理由で止まる
            raise EcoBuildError(
                ErrorCode.NOT_SUPPORTED,
                f"{command} は型 {'・'.join(self.owners)} のモジュールのコマンドです（このモジュールの型：{module.type.name}）。",
                hint="このモジュールで使えるコマンドは ecobuild --help で確かめられます。")

        ctx.exit(run_command(command, action, json_output="--json" in ctx.args))
