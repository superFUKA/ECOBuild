"""アカウントの窓の中身。ログイン中の GitHub のアカウント（頭文字の丸と名前）、そのログインが持つ権限、コミットの作成者、
新しいモジュールの所有者。作成者と所有者は、その場で書き直せる。"""
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
