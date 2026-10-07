from typing import Annotated

from ..._output import run_command


def command(
    all: Annotated[bool, "閉じたIssueも表示する"] = False,
    label: Annotated[str, "このラベルのタスクだけ"] = "",
    assignee: Annotated[str, "この担当者のタスクだけ（@me は自分）"] = "",
    search: Annotated[str, "題名・本文の検索（GitHubの検索の書き方）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（Issue）の一覧を表示します（* は今いる作業空間、+ は手元に作業空間があるもの、- はGitHubにだけあるもの）。"""

    def render(r):
        return "\n".join(("* " if t.current else "+ " if t.workspace else "- " if t.remote else "  ")
                         + f"#{t.number} {t.title}"
                         + "".join(f" [{name}]" for name in t.labels)
                         + (f"（担当：{', '.join(t.assignees)}）" if t.assignees else "")
                         + ("" if t.state == "open" else "（閉じています）") for t in r) or "タスクはありません"

    return run_command("task list", lambda inv: inv.module.tasks(closed=all, label=label or None,
                                                                 assignee=assignee or None, search=search or None),
                       render, json_output=json)
