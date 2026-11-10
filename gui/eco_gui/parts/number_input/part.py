"""数を入れる欄。今の数（value）を欄に入れておき、書き直すと、打った文字を出す（数として読むのはコマンドの側）。"""
from typing import Annotated


def part(
    title: Annotated[str, "見出し"],
    value: Annotated[float | None, "今の数（まだ無ければ null）"] = None,
    placeholder: Annotated[str, "空のときの案内"] = "",
) -> None: ...


def on_changed(text: Annotated[str, "今の文字"]) -> None: ...
