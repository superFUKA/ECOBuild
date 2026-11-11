"""コンテナの要約。環境の作り方・環境とコンテナのイメージ・この作業空間のコンテナ（「古い」「今の作り方」の印）・
この PC にあるこのモジュールのイメージ（今／古い・環境の印・大きさ・作った時・使用中の数）と、「しくみ」の説明。
"""
from typing import Annotated


def part(
    recipe: Annotated[dict | None, "イメージの作り方（{module, environment, image, context}。context が空なら型のひな型）"] = None,
    status: Annotated[dict | None, "この作業空間のコンテナ（{container, state, image, custom_image, outdated}）"] = None,
    images: Annotated[dict | None, "この PC のイメージ（{images: [{name, module, size, created, current, used_by, environment}]}）"] = None,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...
