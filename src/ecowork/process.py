"""外部コマンド（git・gh等）の実行（ecotask.process をそのまま公開する）。

ecobuild 側は ecotask を直接使わず、作業の流れに関わるものは ecowork から使う（層の約束）。
"""

from ecotask.process import Completed, ProcessFailed, find_tool, run

__all__ = ["Completed", "ProcessFailed", "find_tool", "run"]
