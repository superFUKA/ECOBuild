"""GitHubの最新を取り込み、依存先と生成ファイルを最新にします。"""

from typing import Annotated

from ..._output import lines, run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """GitHubの最新を取り込み、依存先と生成ファイルを最新にします。

    作業空間でないブランチは早送り、作業空間は作成元の最新を取り込みます。
    衝突したら、直して ecobuild add の後に ecobuild sync continue（やめるなら ecobuild sync abort）。
    """

    def render(r):
        deps = [f"  依存 {d.name}：{d.action}" + (f"（{d.reason}）" if d.reason else "") for d in r.dependencies]
        return lines(
            f"{r.branch}：" + ("、".join(r.merged) + " を取り込みました" if r.merged else "最新です"),
            "\n".join(deps) if deps else None,
            "生成ファイルを更新しました" if r.regenerated else None,
        )

    return run_command("sync", lambda inv: inv.module.sync(), render, json_output=json)
