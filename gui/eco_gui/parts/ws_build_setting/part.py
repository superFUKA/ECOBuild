"""ビルドと試験の窓の「構成・ビルド設定」。今使われる構成とビルド設定を1行で見せ（「Debug · fast」）、下で選ぶ：

- 構成：ビルド設定のまま（その構成）・Debug・Release（C++ は RelWithDebInfo・MinSizeRel も）。選んでいるものに ✓。この窓だけの選択。
- ビルド設定（この PC で使う）：名前（構成・共有）の並びと「使わない」。使っているものに ✓。なければ、どこで足すかの案内。
- 実行の対象：すべての Project か、Project の名前（種類）。Project のある型（C++）だけ。
- 実行時の引数。

見せ方だけ。選んだものは出力で出す（ビルド設定を使う・やめるは、画面のつなぎが ecobuild profile use を呼ぶ）。
"""
from typing import Annotated


def part(
    profiles: Annotated[dict, "ビルド設定（ecobuild profile list：profiles・selected）"] = {},
    configuration: Annotated[str | None, "この窓で選んでいる構成（空ならビルド設定のまま）"] = "",
    module_type: Annotated[str | None, "モジュールの型（cpp なら、構成に RelWithDebInfo・MinSizeRel も出し、実行の対象も出す）"] = "",
    projects: Annotated[list[dict], "Project（ecobuild project list：name・kind）。C++ のモジュールだけ"] = [],
    target: Annotated[str | None, "選んでいる対象の Project（空なら、すべて）"] = "",
    arguments: Annotated[str | None, "実行時の引数"] = "",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_configuration(value: Annotated[str, "構成の名前（空ならビルド設定のまま）"] = "") -> None: ...


def on_profile(name: Annotated[str, "使うビルド設定の名前（none なら使わない）"]) -> None:
    if not name:
        raise ValueError("ビルド設定の名前が要ります（使わないなら none）")


def on_target(project: Annotated[str, "対象の Project（空なら、すべて）"] = "") -> None: ...


def on_arguments(text: Annotated[str, "実行時の引数"] = "") -> None: ...


def on_settings() -> None: ...
