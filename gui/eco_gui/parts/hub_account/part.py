"""アカウントの窓の中身。ログイン中の GitHub のアカウント（頭文字の丸と名前・GitHub で開く）、ログインし直す・切り替える、
そのログインが持つ権限（足りないものは「権限を追加」）、コミットの作成者、新しいモジュールの所有者。作成者と所有者は、その場で書き直せる。"""
from typing import Annotated


def part(
    account: Annotated[dict | None, "アカウント（{login, scopes}）。まだ読めていなければ null"] = None,
    doctor: Annotated[list[dict], "環境チェックの項目（{id, ok, detail, hint}）。git の名前・メールと、ログインの仕方を読む"] = [],
    config: Annotated[dict, "ツールの設定（{owner}）"] = {},
) -> None: ...


def on_author(name: Annotated[str, "名前"], email: Annotated[str, "メールアドレス"]) -> None:
    if not name.strip() or not email.strip():
        raise ValueError("名前とメールアドレスが要ります")


def on_owner(owner: Annotated[str, "GitHub のユーザー名・組織名"]) -> None:
    if not owner.strip():
        raise ValueError("所有者が要ります")


def on_owner_reset() -> None: ...


def on_login(switch: Annotated[bool, "ログイン済みのアカウントに切り替える（偽なら、別のアカウントでログイン）"] = False) -> None: ...


def on_scope(scope: Annotated[str, "足す権限（project・workflow・delete_repo）"]) -> None:
    if scope not in ("project", "workflow", "delete_repo"):
        raise ValueError("足せる権限は project・workflow・delete_repo です")
