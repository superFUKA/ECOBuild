from typing import Annotated

from ..._output import run_command


def command(
    *paths: Annotated[str, "削除するファイル"],
    test: Annotated[bool, "ライブラリのソースなら、対応するテストファイルも削除する"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルを削除します。ライブラリのソースなら、対応するテストファイルも削除します。"""

    def action(inv):
        changed = [inv.module.remove_file(inv.cwd / path, test=test) for path in paths]
        return {"paths": [p for c in changed for p in c.paths]}

    return run_command("file remove", action, lambda r: "削除しました：\n" + "\n".join(f"  {p}" for p in r["paths"]),
                       json_output=json)
