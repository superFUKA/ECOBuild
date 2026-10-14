from typing import Annotated

from ..._output import run_command


def command(
    name: Annotated[str, "Project名"],
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Projectを外し、そのディレクトリを削除します（他のProjectからのリンクも外します）。"""

    def action(inv):
        inv.confirm(f"Project {name} を外し、ディレクトリを削除しますか？")
        return inv.module.remove_project(name)

    return run_command("project remove", action, lambda r: f"Project {r.project} を外しました：{r.paths[0]}",
                       json_output=json, yes=yes)
