"""Repository の一部：共同作業者・ブランチの保護（複数人での開発）。

Repository（repository.py）がこのクラスを継承する。self は Repository。
"""

from __future__ import annotations

from . import github as _github
from . import model as wm
from .errors import ErrorCode, WorkError


class Members:
    # 共同作業者・ブランチの保護（複数人での開発） -----------------------------------------------

    def members(self, *, share: bool = True) -> list[_github.Member]:
        """共同作業者と招待中の人。share：招待を受けた人にも、タスク管理の情報を共有し直す。"""
        people = self.github.members(self.root)
        if share:
            try:
                self.tracker.share()
            except WorkError as error:   # 共有は添えるだけ（一覧は出す）
                self.notices.append(f"タスク管理の情報を共有できませんでした（{error.message}）。")
        return people

    def add_member(self, login: str, role: str = "write") -> bool:
        """共同作業者に招待する（既に共同作業者なら権限を変える）。招待を送ったら True。"""
        if role not in _github.ROLE_PERMISSIONS:
            raise WorkError(ErrorCode.INVALID_ARGUMENT, f"役割 {role} はありません。",
                            hint=f"{'・'.join(_github.ROLE_PERMISSIONS)} から選んでください。")
        login = login.strip().removeprefix("@")
        if not login:
            raise WorkError(ErrorCode.INVALID_ARGUMENT, "GitHub のユーザー名を指定してください。")
        if login.casefold() == self.github.current_user(self.root).casefold():
            raise WorkError(ErrorCode.INVALID_ARGUMENT, "自分は招待できません。")
        invited = self.github.add_member(self.root, login, role)
        if not invited:
            self.tracker.share()
        return invited

    def remove_member(self, login: str) -> bool:
        """共同作業者から外す（招待中なら招待を取り消す）。担当しているタスクはそのまま（task edit で外す）。"""
        removed = self.github.remove_member(self.root, login.strip().removeprefix("@"))
        if not removed:
            raise WorkError(ErrorCode.INVALID_ARGUMENT, f"{login} は共同作業者でも、招待中でもありません。")
        return removed

    def protection(self, branch: str | None = None) -> _github.Protection | None:
        return self.github.branch_protection(self.root, branch or self.default_base)

    def protect(self, *, approvals: int = 0, require_ci: bool = False,
                branch: str | None = None) -> _github.Protection:
        """タスクブランチでないブランチ（既定は作成元）に、GitHub のブランチの保護を設定する：取り込みは PR だけ、
        承認の数、（require_ci なら）最新のコミットの CI の項目が通っていること、強制 push・削除の禁止。
        管理者は保護を越えられる（1人で使うモジュールの task finish が止まらないように）。"""
        branch = branch or self.default_base
        if wm.is_task_branch(branch):
            raise WorkError(ErrorCode.INVALID_BASE, f"タスクブランチ {branch} は保護しません（タスクブランチでないブランチを守ります）。")
        if approvals < 0 or approvals > 6:
            raise WorkError(ErrorCode.INVALID_ARGUMENT, "承認の数は 0〜6 です。")
        checks: tuple[str, ...] = ()
        if require_ci:
            checks = self.github.check_names(self.root, branch)
            if not checks:
                raise WorkError(ErrorCode.NO_CI_RUN, f"{branch} の最新のコミットに CI の結果がありません。",
                                hint=f"CI を用意して（{self._op('ci init')}）一度動かしてから、もう一度実行してください。")
        protection = _github.Protection(branch, approvals, checks)
        self.github.set_branch_protection(self.root, protection)
        return protection

    def unprotect(self, branch: str | None = None) -> bool:
        return self.github.remove_branch_protection(self.root, branch or self.default_base)
