from typing import Annotated

from ...._output import run_command


def command(discard_local: Annotated[bool, "進行役の作業空間にしかないもの（覚え書き以外の変更等）も捨てる"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """今いるモジュールの進行役の作業空間とコンテナを消します（管理役が残っていれば止めます）。

    進行役の覚え書き（.ecobuild/ai）も消えます。次に agent module start すると、新しく用意します。
    """
    from ecobuild_agent import module_lead as facilitator
    return run_command("agent module close", lambda inv: facilitator.close(inv.module, discard_local=discard_local),
                       lambda r: f"進行役の作業空間を閉じました：{r.root}", json_output=json)
