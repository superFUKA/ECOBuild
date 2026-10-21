from typing import Annotated

from ecobuild.module import mismatch_text

from .._output import lines, run_command, upgrade_note
from .task._show import submission_text
from .workspace.lock import lock_text


def command(
    fetch: Annotated[bool, "GitHubの最新を取得してから表示する（作成元の遅れも表示）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ブランチ、タスクブランチ、変更、提出の状態を表示します。"""

    def render(r):
        if r.reviewing:
            where = (f"#{r.reviewing_task} の提出を確認中（ecobuild task approve／reject {r.reviewing_task}、"
                     "判定せずに戻るなら ecobuild task review --done）") if r.reviewing_task else \
                f"PR #{r.reviewing} を確認中（ecobuild task review --done で戻る）"
        elif r.task:
            where = f"タスクブランチ #{r.task}（{r.branch}、作成元 {r.base}）"
        elif r.branch is None:
            where = "ブランチにいません（切り離された状態。依存先のcloneなら記録の版。作業は ecobuild task start）"
        else:
            where = f"ブランチ {r.branch}"
        excluded = set(r.excluded)
        files = [f"  ステージ済み：{p}" for p in r.staged] + [f"  変更：{p}" for p in r.unstaged] \
            + [f"  新しいファイル：{p}" for p in r.untracked if p not in excluded] + [f"  衝突：{p}" for p in r.conflicted]
        gone = None
        if r.upstream_gone:
            gone = (f"#{r.task} は完了しています（ecobuild task prune {r.task} で片付けられます。"
                    "次の操作でも自動で片付きます）" if r.finished else
                    f"GitHubの {r.branch} は削除されています（別の場所で中止された可能性があります。"
                    f"ecobuild task drop {r.task or ''} で片付けてください）")
        pr = r.pull_request
        return lines(
            where,
            lock_text(r.lock) or None,
            "GitHubのリポジトリはアーカイブ（読み取り専用）されています（ecobuild module unarchive で戻せます）"
            if r.archived else None,
            "取り込みが衝突で止まっています（直して ecobuild sync continue、やめるなら sync abort）" if r.merging else None,
            f"未push：{r.ahead}" if r.ahead else None,
            f"GitHubより遅れています：{r.behind}（ecobuild sync）" if r.behind else None,
            f"作成元 {r.base} より遅れています：{r.base_behind}（ecobuild sync で取り込み）" if r.base_behind else None,
            gone,
            f"提出：{submission_text(pr)} {pr.url}" if pr and not r.finished else None,
            "\n".join(files) if files else "変更はありません",
            "注意：改行コード（CRLF／LF）だけが変わったファイルがあります（中身は同じ。パスなしの task commit は含めません）："
            + ", ".join(r.eol_only) if r.eol_only else None,
            f"管理しない新しいファイル（コミットに含めません。ecobuild track）：{', '.join(r.excluded)}"
            if r.excluded else None,
            "手元の依存先が記録の版と違います（手元のビルドはこの版、CIは記録の版を使います）："
            + mismatch_text(r.dependencies) if r.dependencies else None,
            upgrade_note(r),
        )

    return run_command("status", lambda inv: inv.module.status(fetch=fetch), render, json_output=json)
