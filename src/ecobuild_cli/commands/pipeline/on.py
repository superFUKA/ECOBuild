from typing import Annotated

from ecobuild.config import TIMINGS

from ..._output import run_command, split_list
from ._show import render


def command(
    timing: Annotated[str, f"タイミング（{'・'.join(TIMINGS)}）"],
    names: Annotated[str, "当てるパイプライン（カンマ区切り・この順に走る。外すなら none）"],
    local: Annotated[bool, "このPCだけで足す（ecobuild.local.toml。コミットしない。モジュールの当て方には上乗せするだけ）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タイミングに当てるパイプラインを決めます（今の当て方を置き換えます）。

    before-○○ はその操作の前に走らせ、失敗したら操作を止めます。after-○○ は後に走らせ、失敗は知らせるだけです。
    モジュールの当て方（既定）は ecobuild.toml を変えるので、タスクブランチでだけ変えられます。--local はどこでも。
    """
    chosen = () if names == "none" else tuple(split_list(names))
    return run_command("pipeline on", lambda inv: inv.module.set_trigger(timing, chosen, local=local), render,
                       json_output=json)
