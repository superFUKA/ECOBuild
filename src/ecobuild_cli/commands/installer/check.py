from typing import Annotated

from ... import _self_update
from ..._output import run_command
from .update import render_update


def command(
    ref: Annotated[str, "比べる版（ブランチ・タグ・コミット）。省略時は入れたときの版（ブランチなら、その最新）"] = "",
    json: Annotated[bool, "結果をJSONで出力する（result.up_to_date：最新か）"] = False,
) -> int:
    """ECOBuild の新しい版があるかを確かめます（入れ直しません。何も変えません）。

    入っている版と、GitHub の入れ元の最新を比べます。更新するのは ecobuild installer update。
    """
    return run_command("installer check", lambda inv: _self_update.check(ref or None), render_update, json_output=json)
