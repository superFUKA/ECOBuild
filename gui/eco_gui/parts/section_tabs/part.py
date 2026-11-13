"""ページの上のタブ。左のメニューで選んだまとまりの中を、画面ごとに切り替える。"""
from typing import Annotated


def part(
    items: Annotated[list[dict], "タブ（{id, label, only}）。only があれば、kind がその値のときだけ出す"],
    current: Annotated[str, "今のタブの id"] = "",
    kind: Annotated[str, "モジュールの型（only と照らす）"] = "",
    remember: Annotated[bool, "最後に選んだタブを、この PC に覚える（今のタブがまだ決まっていなければ、覚えたタブを選んだことにする）"] = False,
) -> None: ...


def on_selected(id: Annotated[str, "選んだタブの id"]) -> None:
    if not id:
        raise ValueError("タブの id が要ります")
