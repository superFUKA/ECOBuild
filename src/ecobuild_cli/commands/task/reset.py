"""タスクブランチを以前の版まで戻します（その後のコミットを捨てます）。"""
from typing import Annotated

from ..._output import lines, run_command


def command(
    commit: Annotated[str, "戻す先のコミット（ecobuild log で確かめる。先頭の数文字でよい）"],
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクブランチを以前の版まで戻します（その後のコミットを捨てます）。

    捨てられるのは、まだ GitHub に push していない自分のコミットだけです（push 済みを消すとずれるため）。
    push 済みなら、ecobuild restore --source <コミット> でその版のファイルに戻し、変更としてコミットしてください。
    """

    def action(inv):
        preview = inv.module.reset_task(commit, dry_run=True)
        if not preview.dropped:
            return preview
        listed = "\n".join(f"  {sha[:8]} {subject}" for sha, subject in preview.dropped)
        inv.confirm(f"{preview.branch} を {preview.commit[:8]} まで戻し、次の {len(preview.dropped)} 件のコミットを捨てますか？\n{listed}")
        return inv.module.reset_task(commit)

    def render(r):
        if not r.dropped:
            return f"{r.branch} は既に {r.commit[:8]} です（捨てるコミットはありません）"
        return lines(f"{r.branch} を {r.commit[:8]} まで戻しました（捨てたコミット {len(r.dropped)} 件）",
                     *(f"  {sha[:8]} {subject}" for sha, subject in r.dropped))

    return run_command("task reset", action, render, json_output=json, yes=yes)
