from typing import Annotated

from ..._output import run_command

AGENT = "read"


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """ブランチの一覧を表示します（タスクブランチかどうか、作成元、手元・GitHubのどちらにあるか、以前の仕様のモジュールか）。"""

    def render(branches):
        rows = []
        for b in branches:
            kind = f"タスクブランチ（作成元 {b.base or '?'}）" if b.is_task_branch else "ブランチ"
            where = "・".join(w for w, ok in (("手元", b.local), ("GitHub", b.remote)) if ok)
            if b.merged is not None:
                where += "（取り込み済み）" if b.merged else "（取り込んでいない）"
            if b.format is not None and b.format < b.latest_format:
                where += f"\t以前の仕様（版 {b.format}" + ("）" if b.is_task_branch else f"。module upgrade --branch {b.name}）")
            rows.append(f"{b.name}\t{kind}\t{where}")
        return "\n".join(rows)

    return run_command("branch list", lambda inv: inv.module.branches(), render, json_output=json)
