from typing import Annotated

from ..._output import optional_argument, run_command


def command(
    *number: Annotated[int, "戻す退避の番号（--index と同じ）"],
    index: Annotated[int, "戻す退避の番号（ecobuild stash list の番号。既定：このブランチで最後に退避したもの）"] = -1,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """退避した変更を戻します（番号を省略すると、このブランチで最後に退避したもの）。

    番号は ecobuild stash list の番号です（0 が最後に退避したもの）。ほかのタスクブランチで退避したものは戻せません。

    例：ecobuild stash pop 1
    """
    chosen = optional_argument(number, None if index < 0 else index, "--index", json)
    return run_command("stash pop", lambda inv: inv.module.stash_pop(chosen),
                       lambda r: "退避した変更を戻しました", json_output=json)
