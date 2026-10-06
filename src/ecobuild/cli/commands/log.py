from typing import Annotated

from .._gui_command import open_window
from .._output import run_command


def command(
    *paths: Annotated[str, "このファイル・ディレクトリの履歴だけにする"],
    count: Annotated[int, "表示する件数"] = 20,
    all: Annotated[bool, "すべてのブランチの履歴"] = False,
    gui: Annotated[bool, "TortoiseGitで表示する（Windows）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """履歴を表示します。PRでマージしたコミットには、そのPRの作業空間のIssueを添えます。"""
    if gui:
        return open_window("log", paths, json)

    def render(r):
        return "\n".join(
            f"{e.sha[:7]} {e.date[:10]} {e.author}：{e.subject}" + (f"  [Issue #{e.issue}]" if e.issue else "")
            for e in r) or "履歴はありません"

    return run_command("log", lambda inv: inv.module.log(count=count, paths=paths, all_branches=all), render,
                       json_output=json)
