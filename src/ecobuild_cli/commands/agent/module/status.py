from typing import Annotated

from ecobuild_agent import status as _status
from ...._output import lines, run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """今いるモジュールの進行役の作業空間・様子と、進行役が作った管理役を表示します。"""
    from ecobuild_agent import module_lead as facilitator
    return run_command("agent module status", lambda inv: facilitator.place_status(inv.module), _render, json_output=json)


def _render(r) -> str:
    if not r.exists:
        return lines(f"{r.module} の進行役の作業空間はまだありません（{r.root}）。",
                     "ecobuild agent module start で用意して起動します。")
    state = _status.STATE_NAMES.get(r.state, r.state) if r.running else "動いていない"
    return lines(
        f"進行役（{r.module}）：{state}",
        f"  作業空間：{r.root}（{r.branch or '?'}）",
        f"  コンテナ：{r.container}",
        f"  最後の返答：{r.last_reply}" if r.last_reply else None,
        "管理役：" + ("、".join(f"{m.name}（#{m.task}・{_status.STATE_NAMES.get(m.state, m.state)}）" for m in r.members)
                     if r.members else "なし"),
    )
