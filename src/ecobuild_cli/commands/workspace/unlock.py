from typing import Annotated

from ecobuild import locks as _locks
from ecobuild.results import WorkspaceLocked
from ..._output import lines, run_command
from .lock import lock_text


def command(
    force: Annotated[bool, "非常用：今ある自動のロック（エージェント・実行中のコマンド）も、その原因が続く間だけ無視する"] = False,
    yes: Annotated[bool, "確認せずに実行する（--force のとき）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """手動のロック（ecobuild workspace lock）を外します。

    自動のロック（エージェント・実行中のコマンド）は外せません：原因が終われば外れます。
    --force は非常用です（使用中の作業空間やタスクブランチが消えることがあるため、
    ふだんは使いません）。
    """

    def action(inv):
        root = inv.module.root
        if force and any(r.kind != _locks.MANUAL for r in _locks.status(root).reasons):
            inv.confirm(f"作業空間 {root} の自動のロックを無視します。使用中の作業空間のブランチが入れ替わったり、"
                        "タスクブランチが消えたりして、動いているエージェントやコマンドが壊れることがあります。よろしいですか？")
        _locks.unlock(root, force=force)
        if force:
            inv.module.repository.notices.append(
                "警告：自動のロックを無視しています（その原因が続く間だけ）。使用中の作業空間を変えないでください。")
        return WorkspaceLocked(root, _locks.status(root), forced=force)

    def render(r):
        return lines(f"作業空間 {r.path} の手動のロックを外しました" + ("（自動のロックは無視中）" if r.forced else ""),
                     lock_text(r.lock) or "ロックはありません")

    return run_command("workspace unlock", action, render, json_output=json, yes=yes)
