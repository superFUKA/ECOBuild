from typing import Annotated

from ..._output import run_command
from .protect import render_protection


def command(json: Annotated[bool, "結果をJSONで出力する（保護がなければ result は null）"] = False) -> int:
    """作成元のブランチ（default_base）の、GitHub のブランチの保護の今の設定を表示します（何も変えません）。

    設定する・外すのは ecobuild module protect。GitHub は、保護の設定を管理者にだけ見せます。
    """
    return run_command("module protection", lambda inv: inv.module.repository.protection(), render_protection,
                       json_output=json)
