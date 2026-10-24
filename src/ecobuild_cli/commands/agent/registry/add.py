from typing import Annotated

from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command
from .. import _change
from . import _render


def command(name: Annotated[str, "登録の名前（英小文字・数字・-・_）"],
            from_preset: Annotated[str, "写すプリセットの名前（見本の lead・manager・worker と、このPCのプリセット。agent preset list）"] = "",
            from_dir: Annotated[str, "取り込むフォルダー（agent.toml と agent.md がある）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュールにエージェントの登録を足し、タスクブランチでコミットします。

    置き場所は .ecobuild/agents/registry/<名前>/ です。
    --from-preset でプリセット（見本も）を写すか、--from-dir でフォルダーを取り込みます。どちらもなければ、同じ名前の
    プリセットを写し、それもなければ空の登録を作ります。中身は ecobuild agent registry set で変えます。

    例：
      ecobuild agent registry add reviewer --from-preset worker
    """
    def action(inv):
        added, sha = _change.in_task_branch(inv, f"エージェントの登録「{name}」を足す", lambda module: _registry.add(
            module.root, name, from_preset=from_preset or None, from_dir=from_dir or None))
        return registration_view(added, document=True, pending=True, committed=sha)

    return run_command("agent registry add", action, lambda r: "登録しました：" + _render.details(r), json_output=json)
