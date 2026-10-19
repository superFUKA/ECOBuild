import datetime
from typing import Annotated

from ..._output import run_command


def command(limit: Annotated[int, "表示する件数（新しい順）"] = 20,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業空間でのエージェント（Claude Code）の会話を、新しい順に表示します。

    続きから再開するには ecobuild agent start --agent "claude --resume <id>"。作業空間をコンテナにしていれば、
    コンテナの中の会話（今のブランチでのもの。コンテナが動いているときだけ読めます）。
    """
    return run_command("agent conversations", lambda inv: inv.module.agent_conversations(limit), _render,
                       json_output=json)


def _render(r) -> str:
    if not r.conversations:
        return r.note or "会話はまだありません。"
    return "\n".join(f"{_local(c.updated)}  {c.id}  {c.title}（発言 {c.prompts}{'・' + c.branch if c.branch else ''}）"
                     for c in r.conversations)


def _local(updated: str) -> str:
    try:
        return datetime.datetime.fromisoformat(updated).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return updated
