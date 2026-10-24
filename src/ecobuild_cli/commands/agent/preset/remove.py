from typing import Annotated

from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command


def command(name: Annotated[str, "プリセットの名前"],
            yes: Annotated[bool, "確認せずに実行する"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """このPCのプリセットを消します（文書ごと。同じ名前の見本があれば、また見本が使われます）。見本は消せません。

    モジュールに写した登録は消えません。
    """
    def action(inv):
        if _registry.load_preset(name).source != _registry.PRESET:
            _registry.remove_preset(name)      # 見本は消せない：確認の前に知らせる
        inv.confirm(f"プリセット「{name}」を文書ごと消しますか？")
        return registration_view(_registry.remove_preset(name), document=True)

    return run_command("agent preset remove", action, lambda r: f"プリセット「{r.name}」を消しました",
                       json_output=json, yes=yes)
