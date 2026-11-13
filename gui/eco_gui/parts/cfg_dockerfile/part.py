"""コンテナの環境の Dockerfile（.ecobuild/container/Dockerfile）を書き直す所。今までの GUI の「イメージ（Dockerfile）」のエディター。

上に分かっていること（リポジトリにあるか・材料のハッシュ・イメージがこの PC にあるか・コンテナが古いか）、真ん中に中身、
下に「閉じる」「試しに作る」「保存」と、ECOBuild が重ねる層（読むだけ）。Ctrl+S で保存、Tab で空白4つ。
書けるか（タスクブランチか）・試せるか（Docker が使えるか）は届いた答え（editable・reason・docker_ready）のとおりに、
できないボタンは灰色と理由。保存していない変更があるうちは、閉じる（Esc も）前に確かめる。書きかけで「試しに作る」と、
保存してから作る（build に中身と dirty）。
"""
from typing import Annotated


def part(
    data: Annotated[dict | None, "ecobuild container dockerfile の答え（text・exists・hash・image・image_ready・outdated・container_image・"
                                 "editable・reason・docker_ready・docker_detail）"] = None,
    saved: Annotated[dict | None, "保存した後の答え（ecobuild container dockerfile --write の結果。同じ形に changed）"] = None,
    layer: Annotated[str, "ECOBuild が重ねる層（container recipe の layer）"] = "",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_save(text: Annotated[str, "書く中身"]) -> None:
    if not text.strip():
        raise ValueError("中身が空です")


def on_build(text: Annotated[str, "今の中身（書きかけなら、先に保存する）"] = "",
             dirty: Annotated[bool, "保存していない変更がある（保存してから作る）"] = False) -> None: ...


def on_close() -> None: ...
