from pathlib import Path
from typing import Annotated

from ecobuild import config as _config
from ecobuild import workspaces as _workspaces
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.results import WorkspaceForgotten
from ..._output import run_command


def command(
    path: Annotated[str, "一覧から外す元の clone の場所（ecobuild workspace list に出る場所）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """元の clone（か前の版の作業空間）を、このPCのモジュールの一覧から外します（フォルダには触りません）。

    GitHubのリポジトリにも触りません。作業空間（.ecobuild/w/）は一覧に入っていないので、外すものではありません
    （閉じるなら ecobuild workspace close）。
    """

    def action(inv):
        target = (inv.cwd / path).resolve()
        if (target / ".git").is_file():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{target} は作業空間（git worktree）です。",
                                hint="一覧にあるのは元の clone です。作業空間を閉じるなら ecobuild workspace close。")
        if not _workspaces.forget(target):
            raise EcoBuildError(ErrorCode.WORKSPACE_NOT_RECORDED, f"{target} は一覧にありません。",
                                hint="ecobuild workspace list で、一覧にある場所を確かめてください。")
        return WorkspaceForgotten(target, (Path(target) / _config.FILE_NAME).is_file())

    def render(r):
        text = f"一覧から外しました：{r.path}（フォルダとGitHubのリポジトリはそのままです）"
        return text + ("\nこのフォルダの中で ecobuild を使うと、また一覧に入ります" if r.exists else "")

    return run_command("workspace forget", action, render, json_output=json)
