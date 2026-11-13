"""「表示」：モジュールのページ（ホーム・Project・依存先・パイプライン・エージェント）を、どの場所の中身で見るか。

モジュールのフォルダー（既定のブランチ）か、作業空間のどれか（タスクブランチで未コミットの変更がある所 等）。
作業空間がなければ出さない。選んだ場所は窓を開いている間だけ覚え（memory.window）、同じ窓でほかのページに移っても、
同じ場所を見せる（覚えた場所が届いた値と違えば、changed で戻す）。選んだものは changed で出す（空ならモジュールのフォルダー）。
"""
from typing import Annotated


def part(
    workspaces: Annotated[list[dict] | None, "このモジュールの作業空間（ecobuild module show の workspaces：path・branch・task・review）。読むまで null"] = None,
    value: Annotated[str | None, "今見ている場所（作業空間のフォルダー。モジュールのフォルダーなら空か null）"] = None,
) -> None: ...


def on_changed(path: Annotated[str, "見る場所（作業空間のフォルダー。モジュールのフォルダーなら空）"] = "") -> None: ...
