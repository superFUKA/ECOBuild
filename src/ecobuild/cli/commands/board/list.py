from typing import Annotated

from ..._output import run_command


def command(
    owner: Annotated[str, "ボードの所有者（ユーザー・組織。既定はこのリポジトリの所有者）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """つなげるボード（GitHub Projects）の一覧を表示します。"""

    def render(r):
        return "\n".join(f"{b.title}  {b.url}" + ("（閉じています）" if b.closed else "") for b in r) or (
            "ボードはありません（GitHubで作ってから ecobuild board use <URL> でつなぎます）")

    return run_command("board list", lambda inv: inv.module.boards(owner or None), render, json_output=json)
