from typing import Annotated

from ecobuild_agent import inside as _inside

from ...._output import Invocation, execute, lines


def command(limit: Annotated[int, "出す版の数（新しい順）"] = 30,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """設定 agent_claude_version に選べる版（npm の @anthropic-ai/claude-code の正式な版、新しい順）と、stable・latest が
    どの版かを表示します。読めなければ、そのわけ（版は手で書けます）。"""
    def action(inv):
        tags, versions, reason = _inside.available_versions(limit)
        return {"channels": tags, "versions": list(versions), "reason": reason or None}

    return execute("agent version list", Invocation(json_output=json), action, _render)


def _render(r) -> str:
    channels = "・".join(f"{tag} = {version}" for tag, version in r["channels"].items())
    return lines(channels, "、".join(r["versions"]), r["reason"])
