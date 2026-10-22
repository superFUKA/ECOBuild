from typing import Annotated

from ecobuild_agent import agents as _agents
from ecobuild_agent import children as _children

from ..._output import run_command


def command(id: Annotated[str, "起動し直すエージェントの ID（a- で始まる）"],
            resume: Annotated[bool, "前の会話の続きから起動し直す（既定は新しい会話）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """エージェントを止めて、ECOBuild の係が画面なしで起動し直します。

    作業空間・タスクブランチ・作業（コミット・未コミットの変更・報告）はそのままです。止まった・迷っている・同じところで
    長く作業中のままのエージェントに使います。既定は新しい会話で、任された仕事・途中経過・作業空間の状態からどこまで
    進んだかを確かめてから続けさせます。--resume は前の会話の続きから。
    """
    def action(inv):
        record = _agents.load(id)
        return _children.ask_serve(record, ["agent", "restart", record.id, *(["--resume"] if resume else [])], inv.info)

    return run_command("agent restart", action, _render, json_output=json)


def _render(r: dict) -> str:
    how = "前の会話の続きから" if r.get("resumed") else "新しい会話で"
    return f"「{r.get('name')}」を起動し直しました（{how}・係が画面なしで動かします）。"
