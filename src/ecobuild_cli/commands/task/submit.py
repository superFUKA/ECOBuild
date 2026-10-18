from typing import Annotated

from ..._output import lines, run_command, split_list


def command(
    title: Annotated[str, "提出の題名（既定はタスクの題名。提出済みなら変える）"] = "",
    partial: Annotated[bool, "中間提出にする（承認して取り込んでもタスクを閉じず、タスクブランチを作り直して続ける。自分で取り込むなら task finish --partial）"] = False,
    check: Annotated[bool, "提出の前に ecobuild check（生成ファイル・衝突の印・ビルド・テスト）を行う"] = True,
    draft: Annotated[bool, "下書きとして提出する（完了できない。もう一度 task submit で解除）"] = False,
    reviewer: Annotated[str, "見てもらう人（カンマ区切りのGitHubのユーザー名）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクブランチを提出します（確認 → push → 作成元への提出。タスクブランチでのみ）。

    提出済みなら、新しいコミットを送り直します。下書きは --draft なしでもう一度実行すると解除します。
    未コミットの変更があれば止まります（ecobuild task commit で記録してから）。
    """

    def action(inv):
        return inv.module.submit(title=title or None, partial=partial, draft=draft, reviewers=split_list(reviewer),
                                 check=check, progress=inv.info)

    def render(r):
        kind = "中間提出" if r.partial else "提出"
        return lines(
            f"{'下書きとして' if r.draft else ''}{kind}しました：{r.title}（{r.url}）",
            "次：準備ができたら ecobuild task submit（下書きを解除）" if r.draft
            else "次：ecobuild task finish（CIを待って完了）。見てもらうなら、見る人が ecobuild task review "
                 f"{r.head.removeprefix('task/')} → task approve／reject",
        )

    return run_command("task submit", action, render, json_output=json)
