"""環境チェックの結果。項目ごとに、確認済み（緑）・要対応（橙。必須で足りない）・任意（足りないが、なくても使える）の3段階で見せ、
足りないものには直し方を添える。上に、対応が要る件数のまとめを出す。画面から直せるもの（ログイン・権限の追加）には、直すボタン。"""
from typing import Annotated


def part(
    items: Annotated[list[dict] | None, "項目（{id, name, ok, required, detail, hint, fix}）。まだ確かめていなければ null"] = None,
) -> None: ...


def on_fix(
    fix: Annotated[str, "直し方（ecobuild doctor の fix）：login（ログイン）・scope（権限を追加）"],
    scope: Annotated[str, "scope：足す権限（project 等）"] = "",
) -> None:
    if fix not in ("login", "scope"):
        raise ValueError("直し方は login・scope です")
