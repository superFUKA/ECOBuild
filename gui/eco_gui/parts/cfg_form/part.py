"""入力の窓（フォーム）。題・説明・欄の並び・「キャンセル」と決めるボタン。決めると、欄の値をまとめて出す。

欄（fields）は {name, label, type, …} の並び。type：text・number・textarea・select・radio・checkbox・section・note。
- select・radio：options（[{value, label, help}]）。options_from があれば、読んだ一覧（rows）から作る
  （{"value": 値にする項目, "label": 見せる項目, "note": かっこで添える項目}）。
- section：ここから次の section までを、節にまとめる（label が見出し。collapsed を書けば畳める節で、真なら畳んでおく）。
- show_if：{ほかの欄の名前: 値}（値は並びでもよい）。その値のときだけ出す（出ていない欄の値は出さない）。
- required：空なら、決めるボタンを押せない。empty_uses：空のとき、代わりに出す欄の名前。
- value：初めの値。今の値（values。読んだもの）があれば、そちらが先。value_from：values の中の道筋（a.b）。
  checkbox の on_value：今の値がこれと同じなら、チェックを付けておく。
どの欄を出すか・初めの値は見せ方。何が起きるかは、値を受けたコマンドが決める。
"""
from typing import Annotated, Any


def part(
    title: Annotated[str, "題"],
    fields: Annotated[list[dict], "欄の並び（{name, label, type, value, options, options_from, placeholder, help, show_if, required, empty_uses, collapsed, value_from}）"],
    intro: Annotated[str, "説明（題の下に出す文）"] = "",
    ok: Annotated[str, "決めるボタンの文字"] = "OK",
    danger: Annotated[bool, "決めるボタンを、戻せない操作として赤く見せる"] = False,
    rows: Annotated[list[dict], "select・radio の選べるもの（読んだ一覧。options_from で使う）"] = [],
    values: Annotated[dict | None, "欄の今の値（読んだもの。欄の名前 → 値。なければ value）"] = None,
    at: Annotated[list[str] | None, "values の中の、今の値のある場所（たどる名前の並び。空の名前があれば、今の値はないものとする）"] = None,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_submitted(values: Annotated[dict[str, Any], "欄の名前 → 値（出ている欄だけ）"]) -> None: ...


def on_cancelled() -> None: ...
