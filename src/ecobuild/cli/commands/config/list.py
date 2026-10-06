from typing import Annotated

from .... import tooling
from ..._output import Invocation, execute


def render(values):
    return "\n".join(f"{key} = {values.get(key, '（未設定）')}    # {text}"
                     for key, text in tooling.CONFIG_KEYS.items())


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """ツールの設定の一覧と、設定ファイルの場所を表示します。"""
    return execute("config list", Invocation(json_output=json), lambda inv: tooling.load_config(),
                   lambda r: render(r) + f"\n（{tooling.home() / 'config.toml'}）")
