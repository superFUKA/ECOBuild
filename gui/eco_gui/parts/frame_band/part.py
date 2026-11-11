"""モジュールの窓の帯：モジュールのフォルダー（元の clone）が既定のブランチにいないときの知らせ。

作業は作業空間でするので、元の clone は既定のブランチに置く。違うブランチにいるあいだ、窓の上に出し続ける（× で、この窓では隠す）。
この PC のモジュールの一覧（ecobuild workspace list）から、このモジュールの行を探して出す。当てはまらなければ何も出さない。"""
from typing import Annotated


def part(
    module: Annotated[str, "モジュールのフォルダー"] = "",
    modules: Annotated[list[dict] | None, "この PC のモジュール（ecobuild workspace list の modules：path・exists・branch・default_branch）"] = None,
) -> None: ...
