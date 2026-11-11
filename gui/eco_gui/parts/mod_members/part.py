"""メンバーの表。上に「あなた：アカウント（役割）」と「＋ 招待」。持ち主・組織の行、自分の行の印、招待中の印、役割の変更・外す。

組織のリポジトリだけ、役割を選べる（「役割…」を出す）。個人のリポジトリでは、その注記を出す。
管理者でない（account の admin が偽）ときは、一覧の代わりに説明を出し、「＋ 招待」を灰色にする。
"""
from typing import Annotated


def part(
    members: Annotated[list[dict], "共同作業者と招待中の人（module members：login・role・invited）"] = [],
    account: Annotated[dict, "自分のアカウントと、このモジュールでの役割（account show）"] = {},
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_action(
    action: Annotated[str, "押した操作：invite（招待）・role（役割を変える）・remove（外す・招待を取り消す）"],
    login: Annotated[str, "相手のアカウント（invite では空）"] = "",
    role: Annotated[str, "今の役割（role のとき）"] = "",
    organization: Annotated[bool, "組織のリポジトリか（役割を選べる）"] = False,
) -> None:
    if action not in ("invite", "role", "remove"):
        raise ValueError(f"知らない操作です：{action}")


def on_reload() -> None: ...
