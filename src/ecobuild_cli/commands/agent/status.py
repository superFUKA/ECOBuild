from typing import Annotated

from ecobuild_agent import agents as _agents
from ecobuild_agent import status as _status
from ecobuild_agent import children as _children

from ..._output import lines, run_command


def command(*id: Annotated[str, "エージェントの ID（a- で始まる。省けば今の作業空間のエージェント全員）"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """エージェントの様子（作業中・待機中・止まっている・起動中、今していること、最後の返答）を表示します。

    ID を書けばそのエージェントを、省けば今の作業空間のエージェント全員を出します。係が画面なしで動かしているもの
    （アプリ用の起動）は、使用量・断られた権限も出します。
    """
    def action(inv):
        if id:
            return [shown(_agents.load(one)) for one in id] if len(id) > 1 else shown(_agents.load(id[0]))
        own = _status.own_directory()   # コンテナの中のエージェント：自分
        if own is not None:
            return {**_record(own), "session": _status.session_of(own), **_status.activity(own)}
        root = inv.module.root
        return {"path": root.as_posix(), "agents": [shown(record) for record in _agents.in_workspace(root)]}

    return run_command("agent status", action, _render, json_output=json)


def shown(record: _agents.AgentRecord) -> dict:
    """1人の記録と様子（JSON の形）。"""
    folder = record.folder
    return {**_agents.to_data(record), "session": _status.session_of(folder) or record.session,
            **_status.activity(folder)}


def _record(folder) -> dict:
    data = _status.read(folder / _agents.RECORD)
    return data if isinstance(data, dict) else {}


def _render(r) -> str:
    if isinstance(r, list):
        return "\n\n".join(_one(x) for x in r)
    if "agents" in r:
        return "\n\n".join(_one(x) for x in r["agents"]) or "この作業空間のエージェントはいません。"
    return _one(r)


def _one(r: dict) -> str:
    usage = r.get("usage") or {}
    head = f"「{r['name']}」（{r['id']}・登録 {r.get('registration')}" + ("・手伝い" if r.get("kind") == _agents.HELPER else "") + "）" \
        if r.get("id") else ""
    return lines(
        head or None,
        f"様子：{_children.describe_activity(r) or '不明'}"
        + ("（係が画面なしで動かしています）" if r.get("mode") == _status.APP else ""),
        f"会話：{r['session']}" if r.get("session") else None,
        f"最後の返答：{r['last_reply']}" if r.get("last_reply") else None,
        f"最後の返答の使用量：入力 {usage.get('input_tokens')}・出力 {usage.get('output_tokens')}・"
        f"${usage.get('cost_usd') or 0:.3f}" if usage else None,
        f"断られた権限：{len(r['denials'])} 件" if r.get("denials") else None,
        f"エラー：{r['error']}" if r.get("error") else None,
    )
