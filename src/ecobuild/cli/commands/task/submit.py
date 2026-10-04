from typing import Annotated

from ..._output import run_command


def command(
    title: Annotated[str, "PRのタイトル（既定はIssueのタイトル）"] = "",
    partial: Annotated[bool, "途中の反映にする（マージしてもIssueを閉じず、作業空間を続けて使う）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """作業空間をpushし、作成元へのPRを作成します（作業空間でのみ）。"""

    def action(inv):
        inv.info("生成ファイルを確認しています…")
        return inv.module.require_workspace("PRの作成").submit(title=title or None, partial=partial)

    return run_command("task submit", action, lambda r: f"PR #{r.number}：{r.url}", json_output=json)
