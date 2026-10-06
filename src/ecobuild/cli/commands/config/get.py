from typing import Annotated

from .... import tooling
from ....errors import EcoBuildError, ErrorCode
from ..._output import Invocation, execute


def command(
    key: Annotated[str, "項目"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ツールの設定の値を表示します。"""

    def action(inv):
        if key not in tooling.CONFIG_KEYS:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"設定 {key} はありません。",
                                hint="設定できる項目：" + "、".join(tooling.CONFIG_KEYS))
        return {"key": key, "value": tooling.load_config().get(key)}

    return execute("config get", Invocation(json_output=json), action, lambda r: r["value"] or "（未設定）")
