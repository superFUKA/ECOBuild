"""ハブの上の帯：開発の環境が足りないときの案内（足りないものの名前と「準備する」）。足りなければ何も出さない。"""
from typing import Annotated


def part(
    items: Annotated[list[dict], "環境チェックの項目（{name, ok, required}）"] = [],
) -> None: ...


def on_pressed() -> None: ...
