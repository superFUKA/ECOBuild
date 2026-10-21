from typing import Annotated

from ...._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """今いるモジュールの進行役の作業空間を用意します（起動はしません。なければ作成元から clone、あれば最新へ早送り）。

    画面を持つアプリが、進行役の作業空間の場所で agent module start --here を動かす前に使います。
    """
    from ecobuild_agent import module_lead as facilitator

    def action(inv):
        facilitator.prepare(inv.module, progress=inv.info)
        return facilitator.place_status(inv.module)

    return run_command("agent module prepare", action, lambda r: f"進行役の作業空間を用意しました：{r.root}", json_output=json)
