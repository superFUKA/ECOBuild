from typing import Annotated

from ..._output import lines, optional_argument, run_command
from ..workspace.close import leave, render_removed


def render_apply(r) -> str:
    """task apply の結果。最後の行は何をしたか、その下に次の一手。"""
    if r.partial:
        return lines(
            f"開いていた提出は閉じました（取り込まずに）" if r.closed_submission else None,
            f"タスクブランチを {r.base} の最新から作り直しました" if r.rebuilt else None,
            f"#{r.task} を {r.base} へ反映しました（{r.commit[:7]}。タスクは続きます）：{r.subject}" if r.commit
            else f"#{r.task} の変更はすでに {r.base} に入っていました（タスクは続きます）：{r.subject}",
        )
    done = (f"#{r.task} を {r.base} へ反映し、完了しました（{r.commit[:7]}）：{r.subject}" if r.commit
            else f"#{r.task} の変更はすでに {r.base} に入っていました。入れずに後処理を行い、完了しました：{r.subject}")
    return lines(
        f"開いていた提出は閉じました（取り込まずに）" if r.closed_submission else None,
        f"手元の #{r.task} のタスクブランチを片付けました" + (f"（{r.switched_to} に移りました）" if r.switched_to else "")
        if r.removed else None,
        render_removed(r),
        f"作業空間は後で消せます：残したわけ（使っているシェル・エディター等）を片付けてから、元の clone 等で "
        f"ecobuild task prune --task {r.task}" if r.workspace_kept and not r.removed else None,
        done,
        f"次：ecobuild task start {r.next.number}（{r.next.title}。task next の1番目）" if r.next
        else "次のタスクの候補はありません（ecobuild task list）",
    )


def command(
    *number: Annotated[int, "反映するタスクの番号（--task と同じ）"],
    task: Annotated[int, "反映するタスクの番号（既定は今いるタスクブランチ）"] = 0,
    subject: Annotated[str, "反映するコミットの件名（既定はタスクの題名）"] = "",
    partial: Annotated[bool, "反映してもタスクを閉じず、タスクブランチを作成元の最新から作り直して続ける（中間の反映）"] = False,
    pipelines: Annotated[bool, "取り込みの前のパイプラインを走らせる（ecobuild pipeline。--no-pipelines で省く）"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクを提出せずに作成元へ反映し、完了します（作成元を管理している人の普段の取り込み方）。

    タスクブランチの変更を作成元の最新へ1つのコミットにまとめて push し、タスクを閉じ、タスクブランチと作業空間を
    片付けます。提出（PR）を作らず、CI も待ちません。できるのは作成元への提出を処理できる人（作成元を作った人と
    管理者。子タスクなら親のタスクブランチを作った人）だけです。承認が必須のモジュールでは使えません。開いている
    提出があれば、取り込まずに閉じます。衝突したら何も変えずに止まります（ecobuild sync で作成元を取り込んで直す）。
    コミットの件名は「<題名> (タスク #番号)」です。途中で止まったら、もう一度実行すると続きから行います。
    --partial なら、反映してもタスクを閉じず、タスクブランチを作成元の最新から作り直して続けます（作業空間も残ります）。
    """
    task = optional_argument(number, task, "--task", json)

    def action(inv):
        if not partial:
            leave(inv.module.root, inv)   # この作業空間を消すことがある
        return inv.module.apply(task or None, progress=inv.info, pipelines=pipelines, subject=subject or None,
                                partial=partial)

    return run_command("task apply", action, render_apply, json_output=json)
