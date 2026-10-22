from typing import Annotated

from ..._output import run_command
from ._show import STAGE_NAMES, elsewhere, plan_text, submission_text, with_worker, worker_text, workers

AGENT = "read"


def command(
    all: Annotated[bool, "閉じたIssueも表示する"] = False,
    label: Annotated[str, "このラベルのタスクだけ"] = "",
    assignee: Annotated[str, "この担当者のタスクだけ（@me は自分）"] = "",
    mine: Annotated[bool, "自分が担当のタスクだけ（--assignee @me と同じ）"] = False,
    search: Annotated[str, "題名・本文の検索（GitHubの検索の書き方）"] = "",
    milestone: Annotated[str, "このマイルストーンのタスクだけ"] = "",
    ready: Annotated[bool, "着手できるタスクだけ（依存待ち〔親の依存待ちも〕・開いている子タスク・タスクブランチがなく、未着手のもの）"] = False,
    sprint: Annotated[str, "このスプリントのタスクだけ（スプリントの名前。current は今日を含むもの）"] = "",
    sort: Annotated[str, "並べる値（priority・due・estimate・sprint・planned_start・planned_end・started・created・"
                         "finished。優先度は高い順、日付・見積もりは小さい順）"] = "",
    submitted: Annotated[bool, "提出中のタスクだけ"] = False,
    to_review: Annotated[bool, "自分が見るように頼まれている提出のタスクだけ"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（Issue）の一覧を表示します。

    * は今いるタスクブランチ、+ は手元にタスクブランチがあるもの、- はGitHubにだけあるものです。

    作業空間（.ecobuild/w/<番号>）等、ほかの場所にいるタスクブランチは、その場所も出します。
    作業役（エージェントのチーム）が作業中のタスクは、その作業役と場所を出します（JSON の worker）。
    """
    here = []

    def tasks(inv):
        here.append(inv.module.root)
        found = workers(inv.module.root)
        return [with_worker(t, found) for t in inv.module.tasks(closed=all, label=label or None, assignee="@me" if mine else (assignee or None),
                                search=search or None, milestone=milestone or None, ready=ready,
                                sort=sort or None, sprint=sprint or None, submitted=submitted, to_review=to_review)]

    def render(r):
        return "\n".join(("* " if t.current else "+ " if t.task_branch or t.workspace else "- " if t.remote else "  ")
                         + f"#{t.number} {t.title}"
                         + (f"〈{STAGE_NAMES[t.stage]}〉" if t.stage in STAGE_NAMES else "")
                         + (f"（{submission_text(t.submission)}）" if t.submission else "")
                         + (f" {plan_text(t)}" if plan_text(t) else "")
                         + "".join(f" [{name}]" for name in t.labels)
                         + (f"（担当：{', '.join(t.assignees)}）" if t.assignees else "")
                         + (f"（親 #{t.parent}）" if t.parent else "")
                         + (f"（子 {t.subtasks_done}/{t.subtasks} 完了）" if t.subtasks else "")
                         + (f"（{t.blocked_by} 件を待っています）" if t.blocked_by and t.state == "open" else "")
                         + (f"〔{t.milestone}〕" if t.milestone else "")
                         + ("" if t.state == "open" else "（閉じています）")
                         + (f"（{worker_text(t.worker)}）" if t.worker else elsewhere(t.workspace, here[0]))
                         for t in r) or (
            "着手できるタスクはありません" if ready else "提出中のタスクはありません" if submitted
            else "見るように頼まれている提出はありません" if to_review else "タスクはありません")

    return run_command("task list", tasks, render, json_output=json)
