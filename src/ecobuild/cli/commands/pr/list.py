from typing import Annotated

from ..._output import run_command


def command(
    all: Annotated[bool, "閉じた・マージ済みのPRも表示する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """PRの一覧を表示します（新しい順）。"""

    def render(r):
        return "\n".join(f"#{p.number} {p.title}（{p.head} → {p.base}）"
                         + ("［下書き］" if p.draft else "") + ("［途中の反映］" if p.partial else "")
                         + ("" if p.state == "open" else f"（{p.state}）") for p in r) or "PRはありません"

    return run_command("pr list", lambda inv: inv.module.pull_requests(closed=all), render, json_output=json)
