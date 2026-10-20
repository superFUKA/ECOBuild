"""アプリ用の起動のエージェントの出来事（events.jsonl）の表示：team log・agent log が使う。"""
import json as _json
import time

import click
from ecobuild_agent import status as _status
from ecobuild_agent import team as _team

from ..._output import Invocation, execute


def describe(event: dict) -> str | None:
    """出来事の人向けの1行（なければ None：使用量の知らせ等は出さない）。"""
    kind = event.get("type")
    if kind == "ecobuild":
        if event.get("event") == "start":
            return f"── 起動しました（{_clock(event.get('at'))}・会話 {event.get('session') or '不明'}）"
        if event.get("event") == "exit":
            how = "止めました" if event.get("requested") else "終わりました"
            return f"── {how}（{_clock(event.get('at'))}" + (f"・終了コード {event['code']}" if event.get("code") is not None else "") + "）"
        return None
    if kind == "user":
        content = (event.get("message") or {}).get("content")
        if isinstance(content, str):
            return f"▶ 入力：{_short(content, 300)}"
        failed = [b for b in content or () if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error")]
        return f"    ↳ 失敗：{_short(_text(failed[0].get('content')), 200)}" if failed else None
    if kind == "assistant":
        parts = []
        for block in (event.get("message") or {}).get("content") or ():
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and str(block.get("text") or "").strip():
                parts.append(f"◀ {_short(block['text'], 600)}")
            elif block.get("type") == "tool_use":
                from ecobuild_agent.app import tool_summary
                parts.append(f"  ・{tool_summary(str(block.get('name') or '道具'), block.get('input'))}")
        return "\n".join(parts) or None
    if kind == "result":
        seconds = (event.get("duration_ms") or 0) / 1000
        extra = [f"{seconds:.0f}秒"]
        if isinstance(event.get("total_cost_usd"), (int, float)):
            extra.append(f"${event['total_cost_usd']:.3f}")
        if event.get("permission_denials"):
            extra.append(f"断られた権限 {len(event['permission_denials'])}")
        if event.get("is_error"):
            extra.append(f"エラー {event.get('subtype')}")
        return f"■ 返答の終わり（{'・'.join(extra)}）"
    if kind == "system" and event.get("subtype") == "api_retry":
        return "  （API の一時的な失敗。やり直しています）"
    return None


def render(data: dict) -> str:
    """team log・agent log の表示：様子の1行と、出来事。"""
    activity = data.get("activity") or {}
    head = _team.describe_activity(activity)
    mode = "アプリ用（係）" if activity.get("mode") == _status.APP else ""
    lines = [f"様子：{head}" + (f"  {mode}" if mode else "")] if head else []
    lines += [text for text in (describe(e) for e in data.get("events") or ()) if text]
    return "\n".join(lines) if lines else "出来事はまだありません（係がアプリ用で起動したエージェントだけが記録します）。"


def follow(command: str, read, after: int, json_output: bool, interval: float = 1.0) -> int:
    """read(inv, cursor) → {events, next} を繰り返し、新しい出来事を1つずつ出し続ける（Ctrl+C で止める）。"""
    def action(inv):
        cursor = after
        try:
            while True:
                data = read(inv, cursor)
                for event in data.get("events") or ():
                    text = _json.dumps(event, ensure_ascii=False) if json_output else describe(event)
                    if text:
                        click.echo(text)
                cursor = int(data.get("next") or 0)
                time.sleep(interval)
        except KeyboardInterrupt:
            return {"next": cursor}
    return execute(command, Invocation(json_output=json_output), action, lambda r: None)


def _short(text: str, size: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= size else text[:size - 1] + "…"


def _text(content) -> str:
    if isinstance(content, list):
        return " ".join(str(b.get("text") or "") for b in content if isinstance(b, dict))
    return str(content or "")


def _clock(at) -> str:
    return time.strftime("%m/%d %H:%M", time.localtime(at)) if isinstance(at, (int, float)) else "?"
