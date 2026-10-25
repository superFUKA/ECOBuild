from typing import Annotated

from ..._output import lines, missing, run_command


def command(
    name: Annotated[str, "取り込みたいブランチ（衝突を直したものを、ここへ入れる）"],
    into: Annotated[str, "取り込み先のブランチ（必須）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ブランチ同士の衝突を直すタスクを作って始めます（branch merge <ブランチ> --into <先> が衝突したとき）。

    取り込み先をブランチへ取り込むタスク（作成元はブランチ）を作り、作業空間に取り出して取り込み先を取り込み、
    衝突したところで止めます。作業空間で衝突を直して ecobuild sync continue、ecobuild task apply（または提出）で
    ブランチへ入れると（このタスクはスカッシュせずに履歴ごと入ります）、branch merge <ブランチ> --into <先> が
    早送りで取り込めるようになります。
    """
    if not into:
        return missing("--into", json)

    def render(r):
        return lines(
            f"衝突を直すタスク #{r.task} を作り、作業空間 {r.workspace} で {r.into} を取り込みました。",
            ("衝突したファイル：\n" + "\n".join(f"  {c}" for c in r.conflicts)) if r.conflicts else None,
            (f"次：作業空間で衝突を直して ecobuild sync continue → ecobuild task apply {r.task}（{r.name} へ入れる）"
             if r.conflicts else f"次：ecobuild task apply {r.task}（{r.name} へ入れる）")
            + f" → ecobuild branch merge {r.name} --into {r.into}",
        )

    return run_command("branch resolve", lambda inv: inv.module.resolve_branch_merge(name, into, progress=inv.info),
                       render, json_output=json)
