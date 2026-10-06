from typing import Annotated

from .._output import lines, run_command


def command(
    fetch: Annotated[bool, "GitHubの最新を取得してから表示する（作成元の遅れも表示）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ブランチ、作業空間、変更、PRの状態を表示します。"""

    def render(r):
        if r.reviewing:
            where = f"PR #{r.reviewing} を確認中（ecobuild task review --done で戻る）"
        elif r.workspace:
            where = f"作業空間 #{r.workspace}（{r.branch}、作成元 {r.base}）"
        else:
            where = f"ブランチ {r.branch}"
        files = [f"  ステージ済み：{p}" for p in r.staged] + [f"  変更：{p}" for p in r.unstaged] \
            + [f"  未追跡：{p}" for p in r.untracked] + [f"  衝突：{p}" for p in r.conflicted]
        return lines(
            where,
            "取り込みが衝突で止まっています（ecobuild sync continue／abort）" if r.merging else None,
            f"未push：{r.ahead}" if r.ahead else None,
            f"GitHubより遅れています：{r.behind}（ecobuild sync）" if r.behind else None,
            f"作成元 {r.base} より遅れています：{r.base_behind}（ecobuild sync で取り込み）" if r.base_behind else None,
            f"GitHubの {r.branch} は削除されています（別の場所で反映・中止された可能性があります。"
            "ecobuild task clean か ecobuild task drop で片付けてください）" if r.upstream_gone else None,
            f"PR #{r.pull_request.number}（{r.pull_request.state}）{r.pull_request.url}" if r.pull_request else None,
            "\n".join(files) if files else "変更はありません",
        )

    return run_command("status", lambda inv: inv.module.status(fetch=fetch), render, json_output=json)
