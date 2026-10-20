from typing import Annotated

from ...._output import run_command
from . import _forward


def command(name: Annotated[str, "作業役の名前（か子タスクの番号）"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """人が引き取った作業役を、係に戻します。

    人の画面（対話型）を閉じてから使います。係は同じ会話の続きから画面なしで起動し、任された仕事を続けさせます。
    """
    return run_command("agent team handback", lambda inv: _forward.serve(inv, ["agent", "team", "handback", name]),
                       lambda r: f"「{r.get('name')}」を係に戻しました（会話 {r.get('session')} の続きから）。",
                       json_output=json)
