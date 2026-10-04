from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """ブランチの一覧を表示します（作業空間かどうか、作成元、手元・GitHubのどちらにあるか）。"""

    def render(branches):
        rows = []
        for b in branches:
            kind = f"作業空間（作成元 {b.base or '?'}）" if b.is_workspace else "ブランチ"
            where = "・".join(w for w, ok in (("手元", b.local), ("GitHub", b.remote)) if ok)
            rows.append(f"{b.name}\t{kind}\t{where}")
        return "\n".join(rows)

    return run_command("branch list", lambda inv: inv.module.branches(), render, json_output=json)
