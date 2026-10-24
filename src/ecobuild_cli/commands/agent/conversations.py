import datetime
from typing import Annotated

from ..._output import run_command


def command(limit: Annotated[int, "表示する件数（新しい順）"] = 20,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業空間でのエージェント（Claude Code）の会話を、新しい順に表示します。

    続きから再開するには ecobuild agent start --program "claude --resume <id>"（その会話のエージェントを続きから。
    --as は要りません）。作業空間をコンテナにしていれば、コンテナの中の会話（今のブランチでのもの。コンテナが動いている
    ときだけ読めます）。動いているエージェントの会話（・動いています）は、続きから起動できません（2重になる）。
    """
    return run_command("agent conversations", lambda inv: inv.module.agent_conversations(limit), _render,
                       json_output=json)


def _render(r) -> str:
    from ecobuild_agent import agents
    if not r.conversations:
        return r.note or "会話はまだありません。"

    running = {item["session"] for item in r.running}

    def who(session: str) -> str:
        found = agents.by_session(session)
        return (f"・エージェント「{found.name}」（{found.id}）" if found else "") + ("・動いています" if session in running else "")
    return "\n".join(f"{_local(c.updated)}  {c.id}  {c.title}（発言 {c.prompts}{'・' + c.branch if c.branch else ''}"
                     f"{who(c.id)}）" for c in r.conversations)


def _local(updated: str) -> str:
    try:
        return datetime.datetime.fromisoformat(updated).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return updated
