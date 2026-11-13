"""コンテナの要約。環境の作り方・環境とコンテナのイメージ・この作業空間のコンテナ（「古い」「今の作り方」の印）・
この PC にあるこのモジュールのイメージ（今／古い・環境の印・大きさ・作った時・使用中の数）と、「しくみ」の説明。
上に「作業空間で編集」（Dockerfile のエディター）と、環境の作り方がリポジトリにあれば「場所を開く」（エクスプローラーで
Dockerfile を選んで）、なければ「リポジトリに置く」（今の仕様に合わせる：module upgrade）。押したものは action で出す。
"""
from typing import Annotated


def part(
    recipe: Annotated[dict | None, "イメージの作り方（{module, environment, image, context}。context が空なら型のひな型）"] = None,
    status: Annotated[dict | None, "この作業空間のコンテナ（{container, state, image, custom_image, outdated}）"] = None,
    images: Annotated[dict | None, "この PC のイメージ（{images: [{name, module, size, created, current, used_by, environment}]}）"] = None,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_action(name: Annotated[str, "押したもの：edit（作業空間で編集）・reveal（場所を開く）・place（リポジトリに置く）"]) -> None:
    if name not in ("edit", "reveal", "place"):
        raise ValueError("edit・reveal・place のどれかです")
