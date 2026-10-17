from typing import Annotated

from ecobuild import workspaces as _workspaces
from ..._output import run_command


def command(
    path: Annotated[str, "cloneの場所（モジュールの中ならどこでもよい）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """既にあるモジュールのcloneを、作業空間としてこのPCの記録（ecobuild workspace list）に入れます。

    module new・module clone・task start --dir で作ったものと、中でコマンドを使ったものは自動で記録されます。
    """

    def action(inv):
        root = _workspaces.module_root(inv.cwd / path)
        _workspaces.record(root)
        return next(_workspaces.entry(item) for item in _workspaces.recorded() if _workspaces.same(item.path, root))

    return run_command("workspace add", action,
                       lambda r: f"作業空間として記録しました：{r.path}（{r.repository or r.url or 'GitHubのリポジトリなし'}）",
                       json_output=json)
