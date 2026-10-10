from typing import Annotated

from ..._output import run_command
from ._show import STAGE_NAMES, plan_text


def command(
    all: Annotated[bool, "閉じたIssueも表示する"] = False,
    label: Annotated[str, "このラベルのタスクだけ"] = "",
    assignee: Annotated[str, "この担当者のタスクだけ（@me は自分）"] = "",
    mine: Annotated[bool, "自分が担当のタスクだけ（--assignee @me と同じ）"] = False,
    search: Annotated[str, "題名・本文の検索（GitHubの検索の書き方）"] = "",
    milestone: Annotated[str, "このマイルストーンのタスクだけ"] = "",
    ready: Annotated[bool, "着手できるタスクだけ（依存待ち・開いている子タスク・作業空間がなく、未着手のもの）"] = False,
    sprint: Annotated[str, "このスプリントのタスクだけ（スプリントの名前。current は今日を含むもの）"] = "",
    sort: Annotated[str, "並べる値（priority・due・estimate・sprint・planned_start・planned_end・started・created・"
                         "finished。優先度は高い順、日付・見積もりは小さい順）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（Issue）の一覧を表示します（* は今いる作業空間、+ は手元に作業空間があるもの、- はGitHubにだけあるもの）。"""

    def render(r):
        return "\n".join(("* " if t.current else "+ " if t.workspace else "- " if t.remote else "  ")
                         + f"#{t.number} {t.title}"
                         + (f"〈{STAGE_NAMES[t.stage]}〉" if t.stage in STAGE_NAMES else "")
                         + (f" {plan_text(t)}" if plan_text(t) else "")
                         + "".join(f" [{name}]" for name in t.labels)
                         + (f"（担当：{', '.join(t.assignees)}）" if t.assignees else "")
                         + (f"（親 #{t.parent}）" if t.parent else "")
                         + (f"（子 {t.subtasks_done}/{t.subtasks} 完了）" if t.subtasks else "")
                         + (f"（{t.blocked_by} 件を待っています）" if t.blocked_by and t.state == "open" else "")
                         + (f"〔{t.milestone}〕" if t.milestone else "")
                         + ("" if t.state == "open" else "（閉じています）") for t in r) or (
            "着手できるタスクはありません" if ready else "タスクはありません")

    return run_command("task list", lambda inv: inv.module.tasks(closed=all, label=label or None,
                                                                 assignee="@me" if mine else (assignee or None),
                                                                 search=search or None,
                                                                 milestone=milestone or None, ready=ready,
                                                                 sort=sort or None, sprint=sprint or None),
                       render, json_output=json)
