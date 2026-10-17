from pathlib import Path
from typing import Annotated

from ecobuild import config as _config
from ecobuild import workspaces as _workspaces
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.results import WorkspaceForgotten
from ..._output import run_command


def command(
    path: Annotated[str, "記録から外す作業空間の場所（ecobuild workspace list に出る場所）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """作業空間を、このPCの記録から外します（フォルダには触りません）。

    GitHubのリポジトリにも触りません。場所ごと消すなら ecobuild workspace close です。
    """

    def action(inv):
        target = (inv.cwd / path).resolve()
        if not _workspaces.forget(target):
            raise EcoBuildError(ErrorCode.WORKSPACE_NOT_RECORDED, f"{target} は記録にありません。",
                                hint="ecobuild workspace list で、記録した場所を確かめてください。")
        return WorkspaceForgotten(target, (Path(target) / _config.FILE_NAME).is_file())

    def render(r):
        text = f"記録から外しました：{r.path}（フォルダとGitHubのリポジトリはそのままです）"
        return text + ("\nこのフォルダの中で ecobuild を使うと、また記録されます" if r.exists else "")

    return run_command("workspace forget", action, render, json_output=json)
