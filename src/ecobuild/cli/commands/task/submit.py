from typing import Annotated

from ..._output import run_command


def command(
    title: Annotated[str, "PRのタイトル（既定はIssueのタイトル）"] = "",
    partial: Annotated[bool, "途中の反映にする（マージしてもIssueを閉じず、作業空間を続けて使う）"] = False,
    check: Annotated[bool, "PRを出す前に ecobuild check（ビルド・テスト等）を行う"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """作業空間をpushし、作成元へのPRを作成します（作業空間でのみ）。"""

    def action(inv):
        workspace = inv.module.require_workspace("PRの作成")
        if check:
            inv.info("確認しています（生成ファイル・衝突の印・ビルド・テスト）…")
            inv.module.check()
        inv.info("生成ファイルを確認しています…")
        return workspace.submit(title=title or None, partial=partial)

    return run_command("task submit", action, lambda r: f"PR #{r.number}：{r.url}", json_output=json)
