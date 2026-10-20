"""ヒントに書く操作名と CLI のコマンドの約束（memo/設計.md の「言葉」）。

ライブラリ（ecotask・ecowork・本体・拡張）はヒントに作業の流れの言葉（task commit・sync continue 等）を書き、
プログラム名は使う側が渡す（errors.operation）。CLI はこれと同じ名前のコマンドを持つ。生成するファイル・説明に
書いた「ecobuild <コマンド>」も同じ。CLI のコマンドの名前を変えたら、ここが古い名前の場所を教える。
"""

import functools
import importlib
import re
from pathlib import Path

import click
import pytest

from ecobuild_cli import build_cli

PACKAGES = ("ecoagent", "ecotask", "ecowork", "ecobuild", "ecobuild_cpp", "ecobuild_generic", "ecobuild_python",
            "ecobuild_container", "ecobuild_agent", "ecobuild_bundle", "ecobuild_cli")
# 型ごとのコマンドは、その型のモジュールの中でだけ出る。どれかの型の CLI でたどれればよい
TYPES = ("cpp", "python", "generic")

# op('task commit')・_op("sync continue")・operation(command, 'module new') の操作名
_OPERATION = re.compile(r"""\b_?op(?:eration)?\((?:[^'"()]*,\s*)?['"]([a-z][a-z -]*?)['"]""")
# 文の中の「ecobuild task commit」（ecobuild.toml 等のファイル名は除く）
_WRITTEN = re.compile(r"\becobuild((?: [a-z][a-z-]*)+)")


@functools.cache
def _cli(module_type: str) -> click.Command:
    return build_cli(module_type)


def _resolve(words: list[str]) -> str | None:
    """どの型の CLI でもコマンドとしてたどれなければ、その理由。"""
    reasons = [_resolve_in(_cli(module_type), words) for module_type in TYPES]
    return None if None in reasons else reasons[0]


def _resolve_in(command: click.Command, words: list[str]) -> str | None:
    """コマンドとしてたどれなければ、その理由。グループの次の語は、そのグループのコマンドでなければならない。"""
    for index, word in enumerate(words):
        if not isinstance(command, click.Group):
            return None   # 残りはコマンドの引数（ecobuild task start 4 等）
        found = command.commands.get(word)
        if found is None:
            if index > 0 and getattr(command, "invoke_without_command", False):
                return None   # 引数を取れるグループ（stash 等）
            return f"{' '.join(words[:index]) or '（最上位）'} に {word} というコマンドはありません"
        command = found
    return None


def _uses():
    for package in PACKAGES:
        root = Path(importlib.import_module(package).__file__).parent
        for path in sorted(root.rglob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith(("from ", "import ")):
                    continue
                where = f"{package}/{path.relative_to(root).as_posix()}:{number}"
                for match in _OPERATION.finditer(line):
                    yield where, match.group(1).split()
                for match in _WRITTEN.finditer(line):
                    yield where, match.group(1).split()


def test_operation_names_are_cli_commands():
    problems = [f"{where}：{' '.join(words)}（{reason}）" for where, words in _uses()
                if (reason := _resolve(words)) is not None]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("words", [["task", "commit"], ["sync", "continue"], ["module", "new"], ["build"]])
def test_known_operations_resolve(words):
    assert _resolve(words) is None


def test_unknown_operations_are_reported():
    assert _resolve(["task", "nosuch"]) is not None and _resolve(["nosuch"]) is not None
