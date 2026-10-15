from typing import Annotated

from ..._output import lines, optional_argument, run_command


def render_finish(r) -> str:
    """task finish・task approve の結果。最後の行は何をしたか、その下に次の一手。"""
    waited = [f"  CI {c.workflow}：{c.conclusion}" for c in r.checks]
    if r.partial:
        done = f"中間提出を取り込みました：{r.subject}（#{r.task}。作業空間を作成元の最新から作り直しました）"
        follow = f"次：作業を続けて、終わったら ecobuild task submit → ecobuild task finish {r.task}"
    else:
        done = (f"完了しました：#{r.task} {r.subject}" if not r.resumed
                else f"#{r.task} の止まっていた後処理を行いました：{r.subject}")
        follow = (f"次：ecobuild task start {r.next.number}（{r.next.title}。task next の1番目）" if r.next
                  else "次のタスクの候補はありません（ecobuild task list）")
    return lines(
        "\n".join(waited) or None,
        f"確認の前の場所 {r.returned_to} に戻りました" if r.returned_to else None,
        f"手元の作業空間 task/{r.task} を片付けました" + (f"（{r.switched_to} に移りました）" if r.switched_to else "")
        if r.removed else None,
        ("承認して" if r.approved else "") + done,
        follow,
    )


def command(
    *number: Annotated[int, "完了するタスクの番号（--task と同じ）"],
    task: Annotated[int, "完了するタスクの番号（既定は今いる作業空間）"] = 0,
    wait: Annotated[bool, "CIの結果を待つ（待たない場合、実行中なら止まります）"] = True,
    ignore_checks: Annotated[bool, "CIが失敗していても完了する（待たない）"] = False,
    subject: Annotated[str, "取り込むコミットの件名（既定はタスクの題名）"] = "",
    timeout: Annotated[int, "CIを待つ時間の上限（秒）"] = 1800,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクを完了します：CIを待って取り込み、タスクを閉じ、作業空間を片付けます。

    提出していなければ提出してから取り込みます（1人のモジュールの普段の形）。中間提出なら、取り込んだ後に作業空間を
    作り直して続けます。途中で止まったら、もう一度実行すると続きから行います。
    """
    task = optional_argument(number, task, "--task", json)

    def action(inv):
        if wait and not ignore_checks:
            inv.info("CIの結果を待ってから完了します（ワークフローがあれば）…")
        return inv.module.finish(task or None, wait=wait, ignore_checks=ignore_checks, subject=subject or None,
                                 timeout=timeout)

    return run_command("task finish", action, render_finish, json_output=json)
