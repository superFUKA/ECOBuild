from typing import Annotated

from ecobuild_cli.kit import run_command


def command(
    name: Annotated[str, "移すProject"],
    destination: Annotated[str, "移動先のディレクトリ（モジュールからの相対。まだないもの。例：libs/Math）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Projectのディレクトリを移します（名前は変わりません）。管理ファイルが変わるので、タスクブランチでコミットしてください。"""
    return run_command("project move", lambda inv: inv.module.move_project(name, destination),
                       lambda r: f"{r.project} を {r.paths[0]} へ移しました", json_output=json)
