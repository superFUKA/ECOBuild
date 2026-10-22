from typing import Annotated

from ecobuild_cli._module import Module
from ..._output import run_command
from .lock import lock_text


def command(
    fetch: Annotated[bool, "GitHubの側も確かめる（まだあるか・アーカイブ・名前の変更）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """このPCにある作業空間の一覧（場所・リポジトリ・ブランチ・作業中のタスク）を表示します。

    GitHubにあるモジュールの一覧は ecobuild module list です。作業空間は、module new・module clone・
    task start --dir で作ったときと、モジュールの中でコマンドを使ったときに記録します（ecobuild workspace add でも）。
    移動・削除したフォルダは「見つかりません」と出します（ecobuild workspace forget で記録から外せます）。
    """

    def render(r):
        if not r:
            return ("記録した作業空間はありません（module new・module clone で作るか、"
                    "ecobuild workspace add <場所> で記録できます）")
        return "\n".join(_line(e) for e in r)

    return run_command("workspace list", lambda inv: list(Module.workspaces(fetch=fetch)), render, json_output=json)


def _line(e) -> str:
    if not e.exists:
        return (f"{e.path}：見つかりません（移動・削除したなら ecobuild workspace forget {e.path} で記録から外せます）")
    where = e.branch or "ブランチなし"
    if e.task is not None:
        where += f"＝タスク #{e.task}"
    text = f"{e.path}：{e.repository or e.url or '（GitHubのリポジトリなし）'}（{where}）"
    note = {"archived": "GitHubでアーカイブ（読み取り専用）されています",
            "moved": f"GitHubで名前が {e.moved_to} に変わっています（中で ecobuild sync を実行すると合わせます）",
            "gone": "GitHubにありません（削除されたか、見る権限がありません）",
            "unknown": "GitHubの状態を確かめられませんでした"}.get(e.remote)
    locked = lock_text(e.lock)
    return text + (f"\n  {locked}" if locked else "") + (f"\n  {note}" if note else "")
