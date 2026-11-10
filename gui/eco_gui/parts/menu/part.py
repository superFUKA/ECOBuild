"""左のメニュー。上に窓の題、まとまりごとの項目（アイコン付き）、下にアカウント。折りたためる。"""
from typing import Annotated


def part(
    items: Annotated[list[dict], "項目（{id, label, icon, group, bottom}）。group が変わる所に見出しを出す。bottom が真なら下に寄せる"],
    current: Annotated[str, "今の項目の id"] = "",
    title: Annotated[str, "上に出す題（モジュールの名前など）"] = "",
    account: Annotated[dict, "下に出すアカウント（{login, role}）。なければ出さない"] = {},
) -> None: ...


def on_selected(id: Annotated[str, "選んだ項目の id"]) -> None:
    if not id:
        raise ValueError("項目の id が要ります")


def on_account() -> None: ...
