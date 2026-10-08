from typing import Annotated

from ..._output import run_command


def command(
    all: Annotated[bool, "閉じたIssueも表示する"] = False,
    label: Annotated[str, "このラベルのタスクだけ"] = "",
    assignee: Annotated[str, "この担当者のタスクだけ（@me は自分）"] = "",
    search: Annotated[str, "題名・本文の検索（GitHubの検索の書き方）"] = "",
    milestone: Annotated[str, "このマイルストーンのタスクだけ"] = "",
    ready: Annotated[bool, "着手できるタスクだけ（依存待ち・開いている子タスク・作業空間がなく、ボードでは未着手のもの）"] = False,
    sort: Annotated[str, "ボードのフィールドで並べる（例：Priority。単一選択は選択肢の順、日付・数値は小さい順）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（Issue）の一覧を表示します（* は今いる作業空間、+ は手元に作業空間があるもの、- はGitHubにだけあるもの）。"""

    def render(r):
        return "\n".join(("* " if t.current else "+ " if t.workspace else "- " if t.remote else "  ")
                         + f"#{t.number} {t.title}"
                         + (f"〈{t.status}〉" if t.status else "")
                         + "".join(f" {k}:{v}" for k, v in t.fields.items())
                         + "".join(f" [{name}]" for name in t.labels)
                         + (f"（担当：{', '.join(t.assignees)}）" if t.assignees else "")
                         + (f"（親 #{t.parent}）" if t.parent else "")
                         + (f"（子 {t.subtasks_done}/{t.subtasks} 完了）" if t.subtasks else "")
                         + (f"（{t.blocked_by} 件を待っています）" if t.blocked_by and t.state == "open" else "")
                         + (f"〔{t.milestone}〕" if t.milestone else "")
                         + ("" if t.state == "open" else "（閉じています）") for t in r) or (
            "着手できるタスクはありません" if ready else "タスクはありません")

    return run_command("task list", lambda inv: inv.module.tasks(closed=all, label=label or None,
                                                                 assignee=assignee or None, search=search or None,
                                                                 milestone=milestone or None, ready=ready,
                                                                 sort=sort or None),
                       render, json_output=json)
