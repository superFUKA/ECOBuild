"""何度でも書けるオプション（--env K=V を何度も）。

CLIFrameWork のオプションは1つの値（同じオプションを何度も書くと、最後のものだけ）。そこで click に渡す前に、
打ったコマンドがそのオプションを持つときだけ、何度も書いた値を1つにつなぐ（_output.REPEATED で区切る）。
コマンドは split_repeated（・split_environment）で分けて読む。
"""

from __future__ import annotations

import click

from ._output import REPEATED
from ._suggest import words_of

REPEATABLE = ("--env",)   # 何度でも書けるオプション（値は1つの文字列。コマンドは str で受けて split_repeated で分ける）


def merge(args: list[str], find) -> list[str]:
    """-- より前の、何度も書いた REPEATABLE のオプション（--env A=1 --env B=2・--env=A=1）を、最初の位置に1つにまとめる
    （--env <REPEATED>A=1<REPEATED>B=2）。値を取るオプションの値としての --env（--arguments --env）は数えない。
    find(道筋) → click のコマンド。打ったコマンドがそのオプションを持たない・読めなければ、そのまま。"""
    asked = [name for name in REPEATABLE if any(arg == name or arg.startswith(name + "=") for arg in args)]
    if not asked:
        return args
    try:
        command = find(words_of(args))
        params = command.get_params(click.Context(command)) if command is not None else []
    except Exception:   # まとめるためだけの読み込みでは止めない（実行のときに同じ誤りが出る）
        return args
    options = [p for p in params if isinstance(p, click.Option)]
    names = {name for name in asked if any(name in p.opts and not p.is_flag for p in options)}
    if not names:
        return args
    valued = {name for p in options if not p.is_flag for name in p.opts}   # 後ろに値を取るオプション
    result: list[str] = []
    values: dict[str, list[str]] = {}
    place: dict[str, int] = {}
    index, ended = 0, False
    while index < len(args):
        arg = args[index]
        if not ended and arg == "--":
            ended = True
        name, sep, inline = arg.partition("=")
        if not ended and name in names and (sep or index + 1 < len(args)):
            value = inline if sep else args[index + 1]
            index += 1 if sep else 2
            if name not in place:
                place[name] = len(result)
                result += [name, ""]
            values.setdefault(name, []).append(value)
            continue
        result.append(arg)
        index += 1
        if not ended and arg in valued and index < len(args):   # 値（オプションの名前に見えても）はそのまま
            result.append(args[index])
            index += 1
    for name, position in place.items():
        result[position + 1] = REPEATED + REPEATED.join(values[name])   # 頭にも付ける（空の値を書いたことも分かるように）
    return result
