from typing import Annotated

from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command


def command(name: Annotated[str, "登録の名前"],
            yes: Annotated[bool, "確認せずに実行する"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """ユーザーの登録を消します（文書ごと。同じ名前の見本があれば、また見本が使われます）。見本は消せません。"""
    def action(inv):
        current = _registry.load(name)
        if current.source != _registry.USER:
            _registry.remove(name)      # 見本は消せない：確認の前に知らせる
        inv.confirm(f"登録「{name}」を文書ごと消しますか？")
        return registration_view(_registry.remove(name), document=True)

    return run_command("agent registry remove", action, lambda r: f"登録「{r.name}」を消しました",
                       json_output=json, yes=yes)
