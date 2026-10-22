from typing import Annotated

from .._gui_command import open_window
from .._output import local_time, run_command

AGENT = "read"


def command(
    *paths: Annotated[str, "このファイル・ディレクトリのログだけにする"],
    count: Annotated[int, "表示する件数"] = 20,
    all: Annotated[bool, "すべてのブランチのログ"] = False,
    gui: Annotated[bool, "TortoiseGitで表示する（Windows）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ログ（コミットの一覧）を表示します。PRでマージしたコミットには、そのPRのタスクブランチのIssueを添えます。"""
    if gui:
        return open_window("log", paths, json)

    def render(r):
        return "\n".join(
            f"{e.sha[:7]} {local_time(e.date)} {e.author}：{e.subject}" + (f"  [Issue #{e.issue}]" if e.issue else "")
            for e in r) or "ログはありません"

    return run_command("log", lambda inv: inv.module.repository.log(count=count, paths=paths, all_branches=all), render,
                       json_output=json)
