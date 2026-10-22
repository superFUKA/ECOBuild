from typing import Annotated

from ecobuild_cli.kit import run_command

AGENT = "read"


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """依存関係の図（依存先の依存先も）をツリーで表示します。2回目以降に出てくる依存先は、その先を省きます。"""

    def render(r):
        if not r.direct:
            return f"{r.module}：依存先はありません（ecobuild deps add で追加できます）"
        nodes = {n.name: n for n in r.nodes}
        out, shown = [r.module], set()

        def walk(names, indent):
            for i, name in enumerate(names):
                last = i == len(names) - 1
                node = nodes[name]
                note = ("（cloneなし：ecobuild deps sync で取得すると、その先も分かります）" if not node.present
                        else "（上に同じ）" if name in shown and node.depends_on else "")
                out.append(f"{indent}{'└─ ' if last else '├─ '}{name} {node.revision[:7]}{note}")
                if name in shown:
                    continue
                shown.add(name)
                walk(node.depends_on, indent + ("   " if last else "│  "))

        walk(r.direct, "")
        return "\n".join(out)

    return run_command("deps tree", lambda inv: inv.module.dependency_tree(), render, json_output=json)
