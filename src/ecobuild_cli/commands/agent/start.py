from typing import Annotated

from ..._output import run_command


def command(agent: Annotated[str, "起動するエージェントのコマンド（引数は空白で区切る。既定は claude）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業空間のルートで、エージェントを新しい画面で起動します。

    起動したら待たずに戻ります。エージェントは開いた画面で動き続けます。
    """
    def action(inv):
        return inv.module.start_agent(agent.split()) if agent.strip() else inv.module.start_agent()

    return run_command("agent start", action,
                       lambda r: f"エージェントを起動しました：{' '.join(r.command)}（{r.directory}）", json_output=json)
