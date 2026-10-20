from typing import Annotated

from ecobuild_agent import status as _status
from ecobuild_agent import team as _team

from ..._output import lines, run_command
from . import log


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """この作業空間のエージェントの様子（作業中・待機中・止まっている、今していること、最後の返答）を表示します。

    係が画面なしで動かしているもの（アプリ用の起動）は、使用量・断られた権限も出します（--json：team list の様子と同じ項目）。
    """
    def action(inv):
        folder = log.folder_of(inv.module.root)
        return {"path": inv.module.root.as_posix(), "session": _status.session_of(folder), **_status.activity(folder)}

    return run_command("agent status", action, _render, json_output=json)


def _render(r) -> str:
    usage = r.get("usage") or {}
    return lines(
        f"様子：{_team.describe_activity(r) or '不明'}"
        + ("（係が画面なしで動かしています）" if r.get("mode") == _status.APP else ""),
        f"会話：{r['session']}" if r.get("session") else None,
        f"最後の返答：{r['last_reply']}" if r.get("last_reply") else None,
        f"最後の返答の使用量：入力 {usage.get('input_tokens')}・出力 {usage.get('output_tokens')}・"
        f"${usage.get('cost_usd') or 0:.3f}" if usage else None,
        f"断られた権限：{len(r['denials'])} 件" if r.get("denials") else None,
        f"エラー：{r['error']}" if r.get("error") else None,
    )
