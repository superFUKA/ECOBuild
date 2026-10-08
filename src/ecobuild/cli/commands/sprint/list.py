import datetime
from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """スプリントの一覧を表示します（* は今日を含むもの）。"""
    today = datetime.date.today()

    def render(r):
        return "\n".join(("* " if s.contains(today) else "  ") + f"{s.name}  {s.start.isoformat()}〜"
                         f"{(s.end - datetime.timedelta(days=1)).isoformat()}（{s.days}日）" for s in r) or (
            "スプリントはありません")

    return run_command("sprint list", lambda inv: inv.module.sprints(), render, json_output=json)
