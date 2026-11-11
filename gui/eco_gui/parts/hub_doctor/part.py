"""環境チェックの結果。項目ごとに、確認済み（緑）・要対応（橙。必須で足りない）・任意（足りないが、なくても使える）の3段階で見せ、
足りないものには直し方を添える。上に、対応が要る件数のまとめを出す。"""
from typing import Annotated


def part(
    items: Annotated[list[dict] | None, "項目（{id, name, ok, required, detail, hint}）。まだ確かめていなければ null"] = None,
) -> None: ...
