"""コンテナのイメージのまとめ。モジュールごとに1行：今の作り方のイメージがあるか（今の作り方＝緑・古いものだけ＝橙・まだ作っていません＝灰）、
大きさ・作った時・環境・使っている作業空間・残っている古いものの数。上に、まだ作っていない作業空間と、使っていない古いイメージの数を出す。"""
from typing import Annotated


def part(
    data: Annotated[dict | None, "イメージの一覧（{images: [{name, module, size, created, current, used_by, environment}], docker_ready, docker_detail, missing}）。まだなら null"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...
