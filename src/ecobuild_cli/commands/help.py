from typing import Annotated

import click

from .._output import usage_error


def command(
    *commands: Annotated[str, "使い方を見るコマンド（task start 等。省略すると、コマンドの一覧）"],
    json: Annotated[bool, "コマンドの説明・引数・オプションをJSONで出力する"] = False,
) -> int:
    """コマンドの使い方を表示します（ecobuild <コマンド> --help と同じ。何も変えません）。

    コマンドを省略すると、コマンドの一覧を表示します（ecobuild --help と同じ）。
    --json では、説明・引数・オプション・重さ（effect）を JSON で出します（ecobuild <コマンド> --help --json と同じ）。
    省略したときの JSON は、共通のコマンド（commands）と、型ごとのコマンド（types）のすべてです。

    例：ecobuild help task start
    """
    from .. import TASK_SECTIONS, _catalog, _usage_message, build_cli
    if json:
        return _catalog.emit(build_cli, list(commands), {("task",): TASK_SECTIONS})
    # 人向け：そのコマンドの --help をそのまま出す（ない名前・ほかの型のコマンドの誤りも、打ったときと同じ）
    try:
        return build_cli().main([*commands, "--help"], prog_name="ecobuild", standalone_mode=False) or 0
    except click.UsageError as error:
        return usage_error(_usage_message(error), False, hint="ecobuild help で、コマンドの一覧を確かめてください。")
