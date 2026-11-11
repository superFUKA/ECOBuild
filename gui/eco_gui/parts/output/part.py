"""動かした道具の出力（ログ）を、IDE の出力欄のように見せる。

見出しに、何を動かしたか・状態の印（実行中＝青／成功＝緑／失敗＝赤）・秒数。行はエラー・警告に色を付けて数える
（数を押すと、その行だけにする）。絞り込み・折り返し・コピー・履歴（最近の10回）。終わったら、結果の要約
（試験：成功・失敗・スキップの数と1件ずつの ✗ ✓ -、実行：終了コード、ビルド：成果物、提出前の確認：項目ごとの ✓ ✗）を足す。
行の中の「ファイル(行)」（コンパイラー・Python の知らせ）は、押すと opened を出すリンクにする。"""
from typing import Annotated, Literal


def part(
    lines: Annotated[list[str], "出力の行"] = [],
    title: Annotated[str | None, "何を動かしたか（ビルド・テスト など）"] = "",
    state: Annotated[Literal["", "run", "ok", "bad"] | None, "実行の状態（実行中・成功・失敗）。空なら、印を出さない"] = "",
    kind: Annotated[str | None, "動かしたものの種類（build・rebuild・clean・test・run・check）。結果の要約の作り方が変わる"] = "",
    result: Annotated[dict | None, "終わった実行の結果（ecobuild の result）"] = None,
    fill: Annotated[bool, "置いた場所の高さいっぱいに広げる（下の出力欄）"] = False,
    empty_text: Annotated[str, "まだ出力がないときの文"] = "ここに出力が出ます。",
) -> None: ...


def on_copied(count: Annotated[int, "写した行の数"]) -> None: ...


def on_opened(
    path: Annotated[str, "開くファイル（出力に書いてあったとおり。絶対パスか、動かした場所からの相対）"],
    line: Annotated[int, "行の番号"] = 0,
) -> None:
    if not path:
        raise ValueError("ファイルが要ります")
