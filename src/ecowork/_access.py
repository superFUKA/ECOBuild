"""Repository の一部：アカウントの役割（GitHub の権限）と、それで行えるかの確認。

Repository（repository.py）がこのクラスを継承する。self は Repository。
役割は GitHub が持つ（ECOBuild は表を持たない）。管理（ブランチ・メンバー・保護）は管理者（admin）だけ。
提出の取り込み（承認・差し戻し・完了）は、取り込み先のブランチを作った人と管理者だけ。既定のブランチは管理者だけ。
GitHub が止めるのは admin の部分だけで、取り込みの約束は ECOBuild の中のもの（個人のリポジトリでは GitHub で止められない）。
"""

from __future__ import annotations

from . import github as _github
from .errors import ErrorCode, WorkError

ADMIN = "admin"
# 作業空間（clone）に結び付けたアカウント（git の設定。コミットされず、その clone だけ）。この clone の gh・git は
# そのアカウントとして動く：gh は GH_TOKEN を渡し、git の push は clone の credential.helper がそのアカウントの鍵を渡す。
ACCOUNT_KEY = "ecowork.account"
_HELPER_KEY = "credential.https://github.com.helper"
# その clone の git が GitHub に出す鍵：このPCの gh のそのアカウントの鍵（なければ、渡された GH_TOKEN：コンテナの中）
_HELPER = ('!f() {{ test "$1" = get || exit 0; echo username=x-access-token; '
           'echo "password=$(gh auth token --user {account} 2>/dev/null || printf %s "$GH_TOKEN")"; }}; f')


class Permissions:
    # 作業空間のアカウント ---------------------------------------------------------------------

    @property
    def account(self) -> str | None:
        """この作業空間に結び付けたアカウント（なければ None：gh のログイン中のアカウントで動く）。"""
        return self.git.get_config(ACCOUNT_KEY) or None

    def _use_bound_account(self) -> None:
        """結び付けたアカウントがあれば、gh をそのアカウントとして呼ぶ（Repository を作るときに呼ぶ）。"""
        account = self.account
        if account and hasattr(self.github, "with_account"):
            self.github = self.github.with_account(account)

    def use_account(self, account: str | None) -> str | None:
        """この作業空間を account として動かす（None なら外して、gh のログイン中のアカウントに戻す）。
        コミットの作者（user.name・user.email〔GitHub の noreply〕）も、この clone だけそのアカウントにする。
        account にこのPCの gh でログインしていなければ止める。結び付けたアカウント（ログイン名）を返す。"""
        if account is not None:
            account = account.strip().removeprefix("@")
            if not account or any(c.isspace() or c in "'\"$`;&|<>" for c in account):
                raise WorkError(ErrorCode.INVALID_ARGUMENT, f"アカウントの名前が正しくありません：{account}")
        github = self.github.with_account(account) if hasattr(self.github, "with_account") else self.github
        if account is not None:
            login, number, name = github.identity(self.root)   # ログインしていなければ account_not_logged_in
            self.git.set_config(ACCOUNT_KEY, login)
            self.git.set_config("user.name", name or login)
            self.git.set_config("user.email", f"{number}+{login}@users.noreply.github.com")
            self.git.run("config", "--local", "--unset-all", _HELPER_KEY, check=False)
            self.git.run("config", "--local", "--add", _HELPER_KEY, "")   # 全体の設定の helper を使わない
            self.git.run("config", "--local", "--add", _HELPER_KEY, _HELPER.format(account=login))
        else:
            for key in (ACCOUNT_KEY, "user.name", "user.email"):
                self.git.unset_config(key)
            self.git.run("config", "--local", "--unset-all", _HELPER_KEY, check=False)
        self.github = github
        self._access = self._creators = None
        return self.account

    # アカウントの役割 -----------------------------------------------------------------------

    def access(self) -> _github.Access:
        """ログイン中のアカウントと、このリポジトリでの役割。1回読んだら覚える。"""
        if getattr(self, "_access", None) is None:
            self._access = self.github.access(self.root)
        return self._access

    def is_admin(self) -> bool:
        return self.access().role == ADMIN

    def branch_creator(self, name: str) -> str | None:
        """ブランチを作った人（GitHub の活動の記録。残っていなければ None）。"""
        if getattr(self, "_creators", None) is None:
            self._creators = self.github.branch_creators(self.root)
        return self._creators.get(name)

    def can_take_in(self, base: str) -> bool:
        """base への提出を処理（承認・差し戻し・取り込み）できるか：管理者か、base を作った人（既定のブランチは管理者だけ）。"""
        if self.is_admin():
            return True
        creator = self.branch_creator(base) if base != self.default_base else None
        return creator is not None and creator.casefold() == self.access().login.casefold()

    def take_in_owners(self, base: str) -> str:
        """base への提出を処理できる人（説明に使う）。"""
        creator = self.branch_creator(base) if base != self.default_base else None
        return f"{base} を作った {creator} と管理者" if creator else "管理者"

    def require_admin(self, action: str) -> None:
        """管理者（admin）でなければ止める。"""
        if not self.is_admin():
            access = self.access()
            raise WorkError(ErrorCode.PERMISSION_DENIED, f"{action}は管理者だけが行えます"
                                                         f"（{access.login} の役割は {access.role}）。",
                            hint="管理者に頼むか、管理者に役割を変えてもらってください。",
                            details={"login": access.login, "role": access.role, "required": ADMIN})

    def require_take_in(self, base: str, action: str) -> None:
        """base への提出を処理できなければ止める。"""
        if not self.can_take_in(base):
            access = self.access()
            raise WorkError(ErrorCode.PERMISSION_DENIED, f"{base} への提出の{action}は、{self.take_in_owners(base)}だけが行えます"
                                                         f"（{access.login} の役割は {access.role}）。",
                            hint=f"{self.take_in_owners(base)}に頼んでください。",
                            details={"login": access.login, "role": access.role, "base": base})
