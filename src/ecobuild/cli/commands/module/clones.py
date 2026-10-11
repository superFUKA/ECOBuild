from typing import Annotated

from ....module import Module
from ..._output import run_command

KINDS = {"module": "モジュールのclone", "workspace": "作業空間専用のclone"}


def command(
    fetch: Annotated[bool, "GitHubの側も確かめる（まだあるか・アーカイブ・名前の変更）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """このPCにある、モジュールのcloneの一覧（場所・リポジトリ・種類・ブランチ・作業中のタスク）を表示します。

    GitHubにあるモジュールの一覧は ecobuild module list です。cloneは、module new・module clone・
    task start --dir で作ったときと、モジュールの中でコマンドを使ったときに記録します（ecobuild module register でも）。
    移動・削除したフォルダは「見つかりません」と出します（ecobuild module forget で記録から外せます）。
    """

    def render(r):
        if not r:
            return ("記録したcloneはありません（module new・module clone で作るか、"
                    "ecobuild module register <場所> で記録できます）")
        return "\n".join(_line(e) for e in r)

    return run_command("module clones", lambda inv: list(Module.clones(fetch=fetch)), render, json_output=json)


def _line(e) -> str:
    if not e.exists:
        return (f"{e.path}：見つかりません（移動・削除したなら ecobuild module forget {e.path} で記録から外せます）")
    where = e.branch or "ブランチなし"
    if e.task is not None:
        where += f"＝タスク #{e.task}"
    text = f"{e.path}：{e.repository or e.url or '（GitHubのリポジトリなし）'}（{KINDS[e.kind]}・{where}）"
    note = {"archived": "GitHubでアーカイブ（読み取り専用）されています",
            "moved": f"GitHubで名前が {e.moved_to} に変わっています（中で ecobuild sync を実行すると合わせます）",
            "gone": "GitHubにありません（削除されたか、見る権限がありません）",
            "unknown": "GitHubの状態を確かめられませんでした"}.get(e.remote)
    return text + (f"\n  {note}" if note else "")
