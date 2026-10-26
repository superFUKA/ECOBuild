"""GitHubの最新を取り込み、依存先と生成ファイルを最新にします。"""

from typing import Annotated

from ..._output import lines, run_command

AGENT = "owner"


def command(
    from_branch: Annotated[str, "作成元のほかに取り込むブランチ（GitHub の別の管理ブランチ・別のタスクブランチ。タスクブランチでだけ）"] = "",
    at: Annotated[str, "最新ではなく、このコミットまで取り込む（--from-branch のブランチ、なければ作成元のコミット）"] = "",
    pipelines: Annotated[bool, "取り込んだ後のパイプラインを走らせる（ecobuild pipeline。--no-pipelines で省く）"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """GitHubの最新を取り込み、依存先と生成ファイルを最新にします。

    タスクブランチでないブランチは早送り、タスクブランチは作成元の最新を取り込みます。
    --from-branch <ブランチ> で、作成元のほかのブランチ（別の管理ブランチ・別のタスクブランチ）もタスクブランチへ取り込みます。
    取り込んだコミットは、このタスクブランチの提出にも入ります。
    --at <コミット> で、最新ではなくそのコミットまで取り込みます（選べるコミットは ecobuild log --branch <ブランチ>）。
    衝突したら、直して ecobuild sync continue（直したファイルは自動で登録します。やめるなら ecobuild sync abort）。
    何か取り込んだら、最新の取り込みの後に当てたパイプライン（ecobuild pipeline on）を走らせます。
    """

    def render(r):
        deps = [f"  依存 {d.name}：{d.action}" + (f"（{d.reason}）" if d.reason else "") for d in r.dependencies]
        return lines(
            f"{r.branch}：" + ("、".join(r.merged) + " を取り込みました" if r.merged else "最新です"),
            "\n".join(deps) if deps else None,
            "生成ファイルを更新しました" if r.regenerated else None,
        )

    return run_command("sync", lambda inv: inv.module.sync(progress=inv.info, pipelines=pipelines, from_branch=from_branch, at=at), render,
                       json_output=json)
