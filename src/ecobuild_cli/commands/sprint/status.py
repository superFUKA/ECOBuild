import datetime
from typing import Annotated

from ..._output import lines, optional_argument, run_command
from ..task._show import STAGE_NAMES, task_line


def command(
    *name: Annotated[str, "スプリントの名前（--sprint と同じ）"],
    sprint: Annotated[str, "スプリントの名前（既定：current＝今日を含むもの）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """スプリントの進み具合：段階ごとの数、完了の数、見積もりの合計と残り、残り日数、持ち越し。"""
    chosen = optional_argument(name, sprint, "--sprint", json) or "current"

    def render(r):
        s = r.sprint
        end = (s.end - datetime.timedelta(days=1)).isoformat()
        stages = "・".join(f"{STAGE_NAMES.get(k, '未設定')} {v}" for k, v in r.stages.items())
        return lines(
            f"{s.name}（{s.start.isoformat()}〜{end}）" + ("  今のスプリント" if r.current else "")
            + f"  残り {r.days_left} 日",
            f"タスク：{r.done}/{r.total} 完了" + (f"（{stages}）" if stages else ""),
            f"見積もり：{r.estimate_done:g}/{r.estimate_total:g} 完了・残り {r.estimate_remaining:g}"
            + (f"（見積もりなし：{', '.join(f'#{n}' for n in r.unestimated)}）" if r.unestimated else ""),
            "\n".join(f"  {task_line(t)}" for t in r.tasks) or None,
            "前のスプリントからの持ち越し：\n" + "\n".join(f"  {task_line(t)}" for t in r.carried_over)
            if r.carried_over else None,
        )

    return run_command("sprint status", lambda inv: inv.module.sprint_status(chosen), render, json_output=json)
