"""Repository の一部：使用中の作業空間を、消す・その場で切り替える直前に確かめて守る。self は Repository。

使用中か（エージェントが動いている・コマンドを実行中 等）は利用側が知っているので、Hooks（in_use・branch_in_use）で
受け取る。確かめるのは、この作業空間を消す・その場で切り替える操作と、使用中のほかの作業空間が取り出しているタスクブランチを
消す操作の直前だけ（作業空間はタスクごとなので、ほかのタスクに切り替えられないよう守り続ける必要はない）。
"""

from __future__ import annotations

from .errors import ErrorCode, WorkError


class InUse:
    def _in_use_error(self, action: str, reasons: list[str]) -> WorkError:
        return WorkError(
            ErrorCode.WORKSPACE_IN_USE, f"作業空間が使用中のため、{action}できません。",
            hint="使っているもの（エージェント・実行中のコマンド）が終わってから、もう一度実行してください。",
            details=reasons)

    def _guard_removal(self, branch: str, action: str, *, switching: bool | None = None) -> None:
        """タスクブランチ branch を消す操作 action を、使用中なら止める：使用中のほかの作業空間が取り出しているもの、
        この作業空間が取り出していて（この作業空間を消すか、その場で切り替えて）消すなら、この作業空間が使用中。
        switching：None なら今のブランチかで決める。"""
        if switching is None:
            switching = self.git.current_branch() == branch
        reasons = (self.hooks.in_use(self) if switching else []) + self.hooks.branch_in_use(self, branch)
        if reasons:
            raise self._in_use_error(action, reasons)
