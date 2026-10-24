from typing import Annotated

from ecobuild_bundle import REGISTRY
from ..._output import Invocation, execute


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """登録済みのモジュールの型（ecobuild module new --type で選ぶ）の一覧を表示します。

    new_kinds は module new の --kind で選べるもの（最初に作るもの。ない型は --kind を使いません）。
    icon は型のアイコン（SVG）のファイル、icon_ico は同じアイコンの .ico（どちらも、なければ null）。
    """

    def action(inv):
        result = []
        for e in REGISTRY.entries().values():
            type_class = REGISTRY.load(e.name)
            icon = REGISTRY.icon(e.name)
            ico = icon.with_suffix(".ico") if icon else None
            result.append({"name": e.name, "description": e.description, "implementation": f"{e.module}.{e.cls}",
                           "new_kinds": list(type_class.new_kinds), "default_new_kind": type_class.default_new_kind,
                           "icon": str(icon) if icon else None, "icon_ico": str(ico) if ico and ico.is_file() else None})
        return result

    def render(r):
        return "\n".join(f"{t['name']}：{t['description']}"
                         + (f"（--kind：{'・'.join(t['new_kinds'])}）" if t["new_kinds"] else "") for t in r)

    return execute("module types", Invocation(json_output=json), action, render)
