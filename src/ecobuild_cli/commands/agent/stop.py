from typing import Annotated

from ..._output import run_command


def command(id: Annotated[str, "止めるエージェントの ID（a- で始まる。agent status で見られます）"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """エージェントを止めます（ID で指定します）。

    係が画面なしで動かしているもの（agent start --app）は、係が返答を終えさせてから止めます。人の画面で動いているもの
    は、そのプロセスを止めます。
    """
    def action(inv):
        from ecobuild_agent import stop_agent
        return stop_agent(id, inv.info)

    return run_command("agent stop", action, lambda r: f"エージェント {r.get('id')} を止めました。", json_output=json)
