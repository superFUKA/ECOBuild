from typing import Annotated

from ..._output import missing, run_command


def command(
    name: Annotated[str, "反映するブランチ"],
    into: Annotated[str, "反映先のブランチ（必須）"] = "",
    title: Annotated[str, "PRのタイトル"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ブランチ同士のPRを作成します（例：develop を main へ）。"""
    if not into:
        return missing("--into", json)
    return run_command("branch submit",
                       lambda inv: inv.module.branch(name).submit(into=into, title=title or None),
                       lambda r: f"PR #{r.number} を作成しました：{r.url}", json_output=json)
