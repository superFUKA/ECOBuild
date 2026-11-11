"""オペレーターに頼むことを書いて送る欄。Enter で送る、Shift+Enter で改行。送ると欄は空になる。"""
from typing import Annotated


def part(
    placeholder: Annotated[str, "空のときの案内"] = "",
    label: Annotated[str, "欄の名前（読み上げ用）"] = "オペレーターに頼むこと",
) -> None: ...


def on_sent(text: Annotated[str, "送る文"]) -> None:
    if not text.strip():
        raise ValueError("送る文が空です")
