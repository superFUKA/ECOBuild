from typing import Annotated

from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command
from . import _render


def command(name: Annotated[str, "登録の名前（英小文字・数字・-・_）"],
            from_sample: Annotated[str, "写す見本の名前（lead・manager・worker 等）"] = "",
            from_dir: Annotated[str, "取り込むフォルダー（agent.toml と agent.md がある）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """エージェントの登録を足します（このPCの ECOBUILD_HOME/agents/registry/<名前>/ に置きます）。

    --from-sample で見本を写すか、--from-dir でフォルダーを取り込みます。どちらもなければ、同じ名前の見本を写し
    （見本を自分用に変えるとき）、見本もなければ空の登録を作ります。中身は ecobuild agent registry set で変えます。
    """
    def action(inv):
        return registration_view(_registry.add(name, from_sample=from_sample or None, from_dir=from_dir or None),
                                 document=True)

    return run_command("agent registry add", action, lambda r: "登録しました：" + _render.summary(r),
                       json_output=json)
