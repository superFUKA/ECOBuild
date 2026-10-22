from typing import Annotated

from ecobuild_agent import agents as _agents
from ecobuild_agent import children as _children

from ..._output import run_command


def command(id: Annotated[str, "返すエージェントの ID（a- で始まる）"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """人が引き取ったエージェントを、係に戻します。

    人の画面（対話型）を閉じてから使います。係は同じ会話の続きから画面なしで起動し、任された仕事を続けさせます。
    """
    def action(inv):
        record = _agents.load(id)
        return _children.ask_serve(record, ["agent", "handback", record.id], inv.info)

    return run_command("agent handback", action,
                       lambda r: f"「{r.get('name')}」を係に戻しました（会話 {r.get('session')} の続きから）。",
                       json_output=json)
