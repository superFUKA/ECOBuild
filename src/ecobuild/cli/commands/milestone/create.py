from typing import Annotated

from ..._output import run_command


def command(
    title: Annotated[str, "マイルストーンの題名（例：v1.0）"],
    due: Annotated[str, "期日（YYYY-MM-DD）"] = "",
    description: Annotated[str, "説明"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """マイルストーンを作ります。"""
    return run_command("milestone create",
                       lambda inv: inv.module.create_milestone(title, due=due or None, description=description),
                       lambda r: f"マイルストーン {r.title} を作りました：{r.url}", json_output=json)
