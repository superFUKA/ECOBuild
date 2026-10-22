from typing import Annotated

from ecobuild import workspaces as _workspaces
from ecobuild.errors import EcoBuildError, ErrorCode
from ..._output import run_command


def command(
    path: Annotated[str, "元の clone の場所（モジュールの中ならどこでもよい）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """既にあるモジュールの元の clone を、このPCのモジュールの一覧（ecobuild workspace list）に入れます。

    module new・module clone・module adopt で作ったものと、中でコマンドを使ったものは自動で入ります。
    作業空間（.ecobuild/w/ の git worktree）は元の clone から分かるので、入れません。同じリポジトリの元の clone が
    既にあれば、前の版の作業空間（legacy）として入れます。
    """

    def action(inv):
        root = _workspaces.module_root(inv.cwd / path)
        if (root / ".git").is_file():
            original = _workspaces.original_of(root)
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{root} は作業空間（git worktree）です。",
                                hint=f"一覧に入れるのは元の clone です（{original}）。")
        _workspaces.record(root)
        if any(_workspaces.same(p, root) for p in _workspaces.legacy()):
            inv.notices.append("同じリポジトリの元の clone が既にあるので、前の版の作業空間（legacy）として入れました。")
        return _workspaces.module_entry(root)

    return run_command("workspace add", action,
                       lambda r: f"一覧に入れました：{r.path}（{r.repository or r.url or 'GitHubのリポジトリなし'}）",
                       json_output=json)
