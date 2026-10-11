from typing import Annotated

from .... import clones as _clones
from ..._output import run_command
from .clones import KINDS


def command(
    path: Annotated[str, "cloneの場所（モジュールの中ならどこでもよい）"],
    workspace: Annotated[bool, "作業空間専用のclone（task start --dir で作ったもの等）として記録する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """既にあるモジュールのcloneを、このPCのcloneの記録（ecobuild module clones）に入れます。

    module new・module clone・task start --dir で作ったものと、中でコマンドを使ったものは自動で記録されます。
    """

    def action(inv):
        root = _clones.module_root(inv.cwd / path)
        _clones.record(root, _clones.WORKSPACE if workspace else None)
        return next(_clones.entry(item) for item in _clones.recorded() if _clones.same(item.path, root))

    return run_command("module register", action,
                       lambda r: f"記録しました：{r.path}（{r.repository or r.url or 'GitHubのリポジトリなし'}・{KINDS[r.kind]}）",
                       json_output=json)
