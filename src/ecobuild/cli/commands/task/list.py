from typing import Annotated

from ..._output import run_command


def command(
    all: Annotated[bool, "閉じたIssueも表示する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（Issue）の一覧を表示します（* は今いる作業空間、+ は手元に作業空間があるもの）。"""

    def render(r):
        return "\n".join(("* " if t.current else "+ " if t.workspace else "  ") + f"#{t.number} {t.title}"
                         + ("" if t.state == "open" else "（閉じています）") for t in r) or "タスクはありません"

    return run_command("task list", lambda inv: inv.module.tasks(closed=all), render, json_output=json)
