"""タスクブランチを以前の版まで戻します（その後のコミットを捨てます）。"""
from typing import Annotated

from ..._output import lines, run_command


def command(
    commit: Annotated[str, "戻す先のコミット（ecobuild log で確かめる。先頭の数文字でよい）"],
    keep: Annotated[bool, "ファイルはそのままにして、捨てるコミットの変更をコミットしていない変更として残す（コミットの取り消し）"] = False,
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクブランチを以前の版まで戻します（その後のコミットを捨てます）。

    捨てられるのは、まだ GitHub に push していない自分のコミットだけです（push 済みを消すとずれるため）。
    push 済みなら、ecobuild restore --source <コミット> でその版のファイルに戻し、変更としてコミットしてください。
    --keep では、捨てるコミットの変更がコミットしていない変更として残ります（直前のコミットの取り消し：<コミット>~1）。
    """

    def action(inv):
        preview = inv.module.reset_task(commit, keep=keep, dry_run=True)
        if not preview.dropped:
            return preview
        listed = "\n".join(f"  {sha[:8]} {subject}" for sha, subject in preview.dropped)
        if keep:
            inv.confirm(f"{preview.branch} を {preview.commit[:8]} まで戻し、次の {len(preview.dropped)} 件のコミットを取り消しますか？"
                        f"（変更は手元に残ります）\n{listed}")
        else:
            inv.confirm(f"{preview.branch} を {preview.commit[:8]} まで戻し、次の {len(preview.dropped)} 件のコミットを捨てますか？\n{listed}")
        result = inv.module.reset_task(commit, keep=keep)
        if keep:
            inv.keep_own_changes()   # 取り消した .ecobuild の変更も、変更のまま（自動でコミットし直さない）
        return result

    def render(r):
        if not r.dropped:
            return f"{r.branch} は既に {r.commit[:8]} です（捨てるコミットはありません）"
        if r.kept:
            return lines(f"{r.branch} を {r.commit[:8]} まで戻しました（取り消したコミット {len(r.dropped)} 件。変更は手元に残しています）",
                         *(f"  {sha[:8]} {subject}" for sha, subject in r.dropped))
        return lines(f"{r.branch} を {r.commit[:8]} まで戻しました（捨てたコミット {len(r.dropped)} 件）",
                     *(f"  {sha[:8]} {subject}" for sha, subject in r.dropped))

    return run_command("task reset", action, render, json_output=json, yes=yes)
