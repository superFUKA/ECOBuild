from typing import Annotated

from ecobuild import locks as _locks
from ecobuild.results import WorkspaceLocked
from ..._output import lines, run_command


def lock_text(lock) -> str:
    """ロックの状態の人向けの表示（workspace list・status・lock・unlock で共通）。ロックされていなければ空。"""
    if not lock or not lock.locked:
        return ""
    return "ロック中（使用中）：" + "、".join(r.text for r in lock.reasons)


def command(
    reason: Annotated[str, "ロックの理由（表示に出る）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """今の作業空間をロックします（使用中にする）：ブランチの切り替えと、このタスクブランチを別の作業空間から消す操作を止めます。

    外すまで残ります（ecobuild workspace unlock）。エージェントが動いている間・コンテナが動いている間・
    build／test／run／check の実行中は、自動でロック中になります（こちらは原因が終われば外れます）。
    """

    def action(inv):
        root = inv.module.root
        _locks.lock(root, reason)
        return WorkspaceLocked(root, _locks.status(root))

    return run_command("workspace lock", action,
                       lambda r: lines(f"作業空間 {r.path} をロックしました", lock_text(r.lock)),
                       json_output=json)
