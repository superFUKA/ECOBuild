from pathlib import Path
from typing import Annotated

from ecobuild import clones as _clones
from ecobuild import config as _config
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.results import CloneForgotten
from ..._output import run_command


def command(
    path: Annotated[str, "記録から外すcloneの場所（ecobuild module clones に出る場所）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """cloneを、このPCのcloneの記録から外します。フォルダとGitHubのリポジトリには触りません。"""

    def action(inv):
        target = (inv.cwd / path).resolve()
        if not _clones.forget(target):
            raise EcoBuildError(ErrorCode.CLONE_NOT_RECORDED, f"{target} は記録にありません。",
                                hint="ecobuild module clones で、記録した場所を確かめてください。")
        return CloneForgotten(target, (Path(target) / _config.FILE_NAME).is_file())

    def render(r):
        text = f"記録から外しました：{r.path}（フォルダとGitHubのリポジトリはそのままです）"
        return text + ("\nこのフォルダの中で ecobuild を使うと、また記録されます" if r.exists else "")

    return run_command("module forget", action, render, json_output=json)
