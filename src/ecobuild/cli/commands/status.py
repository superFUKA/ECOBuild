from typing import Annotated

from .._output import lines, run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """ブランチ、作業空間、変更、PRの状態を表示します。"""

    def render(r):
        where = f"作業空間 #{r.workspace}（{r.branch}、作成元 {r.base}）" if r.workspace else f"ブランチ {r.branch}"
        files = [f"  ステージ済み：{p}" for p in r.staged] + [f"  変更：{p}" for p in r.unstaged] \
            + [f"  未追跡：{p}" for p in r.untracked] + [f"  衝突：{p}" for p in r.conflicted]
        return lines(
            where,
            "取り込みが衝突で止まっています（ecobuild sync continue／abort）" if r.merging else None,
            f"未push：{r.ahead}" if r.ahead else None,
            f"PR #{r.pull_request.number}（{r.pull_request.state}）{r.pull_request.url}" if r.pull_request else None,
            "\n".join(files) if files else "変更はありません",
        )

    return run_command("status", lambda inv: inv.module.status(), render, json_output=json)
