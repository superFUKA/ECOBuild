from typing import Annotated

from ..._output import run_command


def command(
    name: Annotated[str, "取り込むブランチ"],
    into: Annotated[str, "取り込み先のブランチ。付けると提出（PR）なしで直接取り込む"] = "",
    ignore_checks: Annotated[bool, "CIが失敗していても取り込む（提出を取り込むとき）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ブランチ同士（タスクブランチでないブランチ）を取り込みます。

    --into <先> を付けると、name を先のブランチへ直接取り込みます（提出〔PR〕を作りません。早送りできれば早送り、
    できなければマージコミット。衝突したら何も変えずに止めます）。付けなければ、ecobuild branch submit で作った
    提出を、マージコミットで取り込みます。
    """
    if into:
        return run_command("branch merge", lambda inv: inv.module.repository.merge_branch_into(name, into),
                           lambda r: f"{name} を {into} へ取り込みました（{r.method}・{r.commit[:7]}）", json_output=json)
    return run_command("branch merge", lambda inv: inv.module.repository.merge_branch(name, ignore_checks=ignore_checks),
                       lambda r: f"{name} の提出を取り込みました（{r.method}）", json_output=json)
