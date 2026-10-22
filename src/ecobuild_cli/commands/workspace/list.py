from typing import Annotated

from ecobuild_cli._module import Module
from ..._output import run_command
from .lock import lock_text


def command(
    fetch: Annotated[bool, "GitHubの側も確かめる（まだあるか・アーカイブ・名前の変更）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """このPCにあるモジュール（元の clone）と、その中の作業空間（場所・ブランチ・作業中のタスク）を表示します。

    GitHubにあるモジュールの一覧は ecobuild module list です。元の clone は、module new・module clone で作ったときと、
    モジュールの中でコマンドを使ったときに一覧に入ります（ecobuild workspace add でも）。作業空間は元の clone の
    .ecobuild/w/ にあり、task start で作って task finish 等で消えます。前の版が作った独立した clone の作業空間は
    「前の版の作業空間」として出します（ecobuild workspace close で閉じられます）。
    移動・削除したフォルダは「見つかりません」と出します（ecobuild workspace forget で一覧から外せます）。
    """

    def action(inv):
        listed = Module.workspaces(fetch=fetch)
        for e in listed.modules:
            if e.exists and e.branch != e.default_branch:
                inv.notices.append(f"元の clone {e.path} が {e.branch or '切り離された状態'} にいます。"
                                   f"既定のブランチ {e.default_branch} に戻してください（git -C \"{e.path}\" switch "
                                   f"{e.default_branch}。作業は作業空間でします）。")
        return listed

    def render(r):
        if not r.modules and not r.legacy:
            return ("このPCのモジュールはありません（module new・module clone で作るか、"
                    "ecobuild workspace add <場所> で一覧に入れられます）")
        parts = [_line(e) for e in r.modules]
        if r.legacy:
            parts.append("前の版の作業空間（ecobuild workspace close で閉じられます）：")
            parts += ["  " + _line(e) for e in r.legacy]
        return "\n".join(parts)

    return run_command("workspace list", action, render, json_output=json)


def _line(e) -> str:
    if not e.exists:
        return (f"{e.path}：見つかりません（移動・削除したなら ecobuild workspace forget {e.path} で一覧から外せます）")
    where = e.branch or "ブランチなし"
    if e.task is not None:
        where += f"＝タスク #{e.task}"
    text = f"{e.path}：{e.repository or e.url or '（GitHubのリポジトリなし）'}（{where}）"
    note = {"archived": "GitHubでアーカイブ（読み取り専用）されています",
            "moved": f"GitHubで名前が {e.moved_to} に変わっています（中で ecobuild sync を実行すると合わせます）",
            "gone": "GitHubにありません（削除されたか、見る権限がありません）",
            "unknown": "GitHubの状態を確かめられませんでした"}.get(e.remote)
    locked = lock_text(e.lock)
    text += (f"\n  {locked}" if locked else "") + (f"\n  {note}" if note else "")
    for w in getattr(e, "workspaces", ()):
        state = (f"確認中 PR #{w.review}" if w.review is not None else w.branch or "ブランチなし") + \
            (f"＝タスク #{w.task}" if w.task is not None else "")
        text += f"\n  作業空間 {w.name}：{w.path}（{state}" + (f"・{w.account}" if w.account else "") + "）"
        if lock_text(w.lock):
            text += f"\n    {lock_text(w.lock)}"
    return text
