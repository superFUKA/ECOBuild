"""ビルド設定の表。「この PC で使う」をラジオで選び、行ごとに編集・Project ごとの上書き・削除。

列は、モジュールの型（kind）で変わる：C++ は「ライブラリ」「並列数」「そのほか・Project ごとの上書き」、
Python は「並列数」も。C++ のオプションは言葉にして見せる（C++ 20・生成器 Ninja …）。Project ごとの上書きは、
Project の印と中身、その場の「変更」「外す」。空のときは、作り方の案内を出す。
"""
from typing import Annotated


def part(
    data: Annotated[dict | None, "ビルド設定（{selected: この PC で使う名前か null, profiles: {名前: {configuration, parallel, shared, options, projects}}}）"] = None,
    kind: Annotated[str, "モジュールの型（cpp・python・generic。列と、編集の窓の出し分けに使う）"] = "",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_use(name: Annotated[str, "この PC で使うビルド設定の名前（使わないなら none）"]) -> None:
    if not name:
        raise ValueError("名前が要ります")


def on_add(kind: Annotated[str, "モジュールの型"]) -> None: ...


def on_edit(name: Annotated[str, "編集するビルド設定の名前"], kind: Annotated[str, "モジュールの型"]) -> None:
    if not name:
        raise ValueError("名前が要ります")


def on_remove(name: Annotated[str, "削除するビルド設定の名前"]) -> None:
    if not name:
        raise ValueError("名前が要ります")


def on_project(name: Annotated[str, "ビルド設定の名前"],
               project: Annotated[str, "上書きを変える Project（新しく足すなら空）"] = "") -> None:
    if not name:
        raise ValueError("名前が要ります")


def on_project_clear(name: Annotated[str, "ビルド設定の名前"], project: Annotated[str, "上書きを外す Project"]) -> None:
    if not name or not project:
        raise ValueError("ビルド設定と Project の名前が要ります")
