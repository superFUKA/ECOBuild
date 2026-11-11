"""パイプラインのカードの並び。名前、手順の印を → でつないだ列、流す試験、当てているタイミング。カードのボタン：▶ 実行・編集…・削除…。

上に「＋ パイプライン」。編集・削除を押すと、今の中身（手順・試験・当てているタイミング）を添えて出す（入力の窓の初めの値・説明に使う）。
"""
from typing import Annotated


def part(
    data: Annotated[dict, "パイプラインと当て方（pipeline list：pipelines・triggers・local）"] = {},
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_action(
    action: Annotated[str, "押した操作：add（作る）・run（実行）・edit（編集）・remove（削除）"],
    name: Annotated[str, "パイプラインの名前（add では空）"] = "",
    steps: Annotated[str, "今の手順（カンマ区切り）"] = "",
    tests: Annotated[str, "今の流す試験（カンマ区切り）"] = "",
    used: Annotated[str, "当てているタイミングを書いた文（削除の窓の説明に出す。なければ空）"] = "",
) -> None:
    if action not in ("add", "run", "edit", "remove"):
        raise ValueError(f"知らない操作です：{action}")


def on_reload() -> None: ...
