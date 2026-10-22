"""Repository の一部：使用中の作業空間（ロック中）を守る。self は Repository。

ロックの判断（エージェント・コンテナ・実行中のコマンド等）は利用側が知っているので、Hooks（switch_locks・branch_locks）で
受け取る。守るのは、この作業空間を消す・その場で切り替える操作と、ロック中のほかの作業空間が使っているタスクブランチを消す操作。
"""

from __future__ import annotations

from .errors import ErrorCode, WorkError


class Locking:
    def _locked_error(self, action: str, reasons: list[str]) -> WorkError:
        return WorkError(
            ErrorCode.WORKSPACE_LOCKED, f"作業空間が使用中（ロック中）のため、{action}できません。",
            hint="ロックの原因を終わらせてから、もう一度実行してください（エージェントを止める・コンテナを止める・"
                 f"実行中のコマンドが終わるのを待つ。手動のロックなら {self._op('workspace unlock')} で外せます）。",
            details=reasons)

    def _guard_removal(self, branch: str, action: str, *, switching: bool | None = None) -> None:
        """タスクブランチ branch を消す操作 action を、ロックで止める：ロック中のほかの作業空間が使っているもの、
        この作業空間が取り出していて（この作業空間を消すか、その場で切り替えて）消すなら、この作業空間のロック。
        switching：None なら今のブランチかで決める。"""
        if switching is None:
            switching = self.git.current_branch() == branch
        reasons = (self.hooks.switch_locks(self) if switching else []) + self.hooks.branch_locks(self, branch)
        if reasons:
            raise self._locked_error(action, reasons)
