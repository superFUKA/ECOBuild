from typing import Annotated

from ..._output import lines, missing, run_command


def command(
    name: Annotated[str, "反映するブランチ"],
    into: Annotated[str, "反映先のブランチ（必須）"] = "",
    title: Annotated[str, "提出の題名"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ブランチ同士の提出（PR）を作ります（例：develop を main へ）。

    取り込むのは ecobuild branch merge <ブランチ>。
    """
    if not into:
        return missing("--into", json)
    return run_command("branch submit",
                       lambda inv: inv.module.branch(name).submit(into=into, title=title or None),
                       lambda r: lines(f"{name} を {into} へ提出しました：{r.url}",
                                       f"次：ecobuild branch merge {name}"), json_output=json)
