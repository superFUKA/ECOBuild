from typing import Annotated

from ... import module_type
from .._output import Invocation, execute


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """登録済みのモジュールの型（ecobuild new --type で選ぶ）の一覧を表示します。"""

    def action(inv):
        return [{"name": e.name, "description": e.description, "implementation": f"{e.module}.{e.cls}"}
                for e in module_type.entries().values()]

    return execute("types", Invocation(json_output=json), action,
                   lambda r: "\n".join(f"{t['name']}：{t['description']}" for t in r))
