"""CI の設定のカード。ワークフローのパスと状態の印（なし・手で編集・今の設定のとおり・違う）、OS・構成・共有ライブラリ・ブランチ。

「CIを用意する…／設定を変える…」と「CIをやめる…」を押すと、今の設定を添えて出す（入力の窓の初めの値に使う）。
管理者でない人（admin が偽）には、どちらも灰色と理由「管理者だけが行えます」。
作り直した結果に非公開の依存先（private）があれば、CI で取得するにはトークンが要ることを帯で知らせる。
"""
from typing import Annotated


def part(
    data: Annotated[dict, "CI の設定（ci show）"] = {},
    admin: Annotated[bool | None, "このモジュールの管理者か（account show の admin。分からないあいだは null）"] = None,
    private: Annotated[list[str] | None, "作り直したときに分かった、非公開の依存先（ci init の private_dependencies）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_action(
    action: Annotated[str, "押した操作：init（用意する・設定を変える）・remove（やめる）"],
    os: Annotated[str, "今の OS（カンマ区切り。型の既定なら空）"] = "",
    configuration: Annotated[str, "今の構成（カンマ区切り）"] = "",
    shared: Annotated[str, "共有ライブラリでもビルドするか（on・off）"] = "off",
    branches: Annotated[str, "push で動かすブランチ（カンマ区切り。既定なら空）"] = "",
    edited: Annotated[bool, "ワークフローが手で編集されているか（上書きの欄を出す）"] = False,
) -> None:
    if action not in ("init", "remove"):
        raise ValueError(f"知らない操作です：{action}")


def on_reload() -> None: ...
