from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode

from ..._output import lines, run_command, split_list, split_semicolons

AGENT = "owner"


def command(
    title: Annotated[str, "提出の題名（既定はタスクの題名。提出済みなら変える）"] = "",
    partial: Annotated[bool, "中間提出にする（取り込まれてもタスクを閉じず、タスクブランチを作り直して続ける。提出済みなら切り替える）"] = False,
    complete: Annotated[bool, "取り込まれたらタスクを完了する（新しい提出の既定。提出済みの中間提出を切り替える）"] = False,
    check: Annotated[bool, "提出の前・後に当てたパイプライン（ecobuild pipeline on。既定はなし）を走らせる"] = True,
    draft: Annotated[bool, "下書きとして提出する（完了できない。もう一度 task submit で解除）"] = False,
    reviewer: Annotated[str, "見てもらう人（カンマ区切りのGitHubのユーザー名）"] = "",
    note: Annotated[str, "提出の説明（変えたこと・確かめたこと・影響する所・戻し方。提出済みなら書き換える）"] = "",
    verified_by: Annotated[str, "提出した人が確かめたこと（「<コマンド>=<結果>」。複数はセミコロン区切り。--no-check で出すときの証拠として確認欄に並べる）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクブランチを提出します（確認 → push → 作成元への提出。タスクブランチでのみ）。

    提出済みなら、新しいコミットを送り直します。下書きは --draft なしでもう一度実行すると解除します。
    取り込まれたらタスクを完了するか（--complete／--partial）は、提出済みなら指定したときだけ変えます。
    提出の前・後に走らせるパイプラインは ecobuild pipeline on で当てます（既定は何もしません）。前のものが失敗したら出しません。
    提出の本文には、確認の結果（どの版で何が通ったか）を書きます（出し直すと今の版のものに）。
    --no-check で出すときは、自分で確かめたことを --verified-by "pytest tests/unit=成功 12" の形で確認欄に書けます。
    未コミットの変更があれば止まります（ecobuild task commit で記録してから）。
    """

    def action(inv):
        if partial and complete:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--partial と --complete は一緒に使えません。")
        return inv.module.submit(title=title or None, partial=True if partial else False if complete else None,
                                 draft=draft, reviewers=split_list(reviewer), check=check, note=note or None,
                                 verified_by=split_semicolons(verified_by), progress=inv.info)

    def render(r):
        kind = "中間提出" if r.partial else "提出"
        return lines(
            f"{'下書きとして' if r.draft else ''}{kind}しました：{r.title}（{r.url}）",
            "取り込まれてもタスクは閉じません（タスクブランチを作り直して続けます）。" if r.partial
            else "取り込まれたらタスクを完了します。",
            "次：準備ができたら ecobuild task submit（下書きを解除）" if r.draft
            else "次：ecobuild task finish（CIを待って取り込む）。見てもらうなら、見る人が ecobuild task review "
                 f"{r.head.removeprefix('task/').split('-')[0]} → task approve／reject",
        )

    return run_command("task submit", action, render, json_output=json)
