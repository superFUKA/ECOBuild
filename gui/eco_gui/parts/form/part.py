"""入力の窓（フォーム）。題・説明・「何が起きるか」の表・欄の並び・「キャンセル」と決めるボタン。どの画面の入力の窓も、この部品1つで描く。

決める（ボタン・Enter・Ctrl+Enter）と、出ている欄の値をまとめて出す。どのコマンドを呼ぶかは、画面のつなぎが決める。
ここでするのは見せ方だけ：欄の出し分け・初めの値・必須の欄の確かめ・値の形（つないだ文字など）。何が起きるかは、値を受けたコマンドが決める。

欄（fields）は {name, label, type, …} の並び。
- type：text（既定）・number・date・textarea・select・radio・checkbox・checks（いくつか選ぶ）・section・note（文だけ）
- placeholder・help（下に小さく出す文）・required（題に * が付き、空では決められない）・rows（textarea）・min・step（number）
- value：初めの値。initial（名前 → 値）にあれば、そちら。読んだ今の値（values）があれば、それがいちばん先。
  value_from：読んだ値（vars・values）の中の道筋（a.b）。checkbox の on_value／off_value：読んだ値がこれと同じなら、印を付ける／外す。
- select・radio・checks の選べるもの：options（[{value, label, help}]）か、options_from（読んだ一覧から）：
  {"source": "rows" か "more", "value": 値にする項目, "label": 見せる項目, "note": かっこで添える項目（並びでもよい）,
   "note_labels": {値: 見せる言葉}, "where": {項目: 値}（合う行だけ）}
  select の none_label：いちばん上に置く「選ばない」。empty_text：選べるものがないときの文。
- radio の inline：横に並べる。columns：この数の列に並べる。strong：選ぶものの名前を太字に。label_hidden：題を見せない（読み上げにだけ出す）。
  checkbox の strong：太字。
- suggestions（text）：打つときの候補（[{value, label}]）。suggestions_from：読んだ一覧から（options_from と同じ書き方）。
  読んだ一覧から選ぶ欄・候補のある欄は、一覧が届くまで「候補を読み込んでいます…」を欄の下に出す（窓は待たせない。届いたら足す）。
- candidates（text）：欄の下に並べる候補（[{value, label, help}]。押すと欄に入る。null なら、まだ届いていない）。
  candidates_title・candidates_empty・candidates_loading：その上の文・1つもないときの文・届くまでの文。
- hint（text）：欄のツールチップ。
- row：同じ名前の欄を、横に並べる。width：その行の中での幅の割合（既定は 1）。
- multiple（text）：＋ で欄を足し、× で消す。値は入れたものの並び。
- show_if・hide_if：{名前: 値}（値は並びでもよい）。名前は、ほかの欄か、読んだ値（vars・values）の道筋。合うときだけ出す／隠す
  （出ていない欄の値は出さない）。
- 出す値の形：join（checks・multiple を、この文字でつないだ1つの文字に。empty は1つもないときの値）、
  checkbox の on・off（真偽の代わりに出す値）・inverse（逆の真偽を、この名前でも出す）、
  empty_uses（空のとき、代わりに出す欄の名前）。text は前後の空白を除き、number は数にする。
- section：ここから次の section までを節にまとめる（label が見出し、note が横の小さな文。collapsed を書けば畳める節で、真なら畳んでおく。
  open が真なら開けておく。{"type": "section", "end": True} で節を終える）。
- note：label の文を出す。tone（bad・warn・info）で帯にする。list_from：下に並べる名前の並び（読んだ値の道筋）。
  並びが空なら出さない（衝突するファイルがないときの警告など）。empty_text があれば、読み終えた後、代わりにその文を出す
  （読んだ値に、その並びがないときは出さない）。list_as が "commits" なら、「sha 件名」の並びを、入るコミットの箱で出す。

「何が起きるか」の表（outcome）は {label, text, show_if, hide_if} の並び（欄の値で、出る行が変わる）。
決めるほかにできること（actions）は {name, label, hint, primary, show_if, hide_if} の並び。ボタンの行の左に置き、押すと名前と今の値を出す。
題・説明・表・欄の文の中の {道筋} は、vars（画面が渡す値）・values（読んだ値）・also（もう1つの読んだ値）のその値に置き換わる
（空なら、中身のないかっこごと消える。並びの数は {道筋.length}）。

描く所は、共有のコード（gui/eco_gui/lib.js の form）にある。欄を読んだ情報から組む部品（task-form・hub-add-form）も、それを使う。
"""
from typing import Annotated, Any


def part(
    fields: Annotated[list[dict], "欄の並び"],
    title: Annotated[str, "題"] = "",
    subject: Annotated[str, "題の後ろに「：」で続ける、何についてか（名前など）"] = "",
    intro: Annotated[str, "説明（題の下に出す文）"] = "",
    detail: Annotated[str, "説明の下に出す文（対象ごとに変わる説明。空なら出さない）"] = "",
    outcome: Annotated[list[dict], "「何が起きるか」の表（{label, text, show_if, hide_if}）"] = [],
    actions: Annotated[list[dict], "決めるほかにできること（{name, label, hint, primary, show_if, hide_if}。ボタンの行の左に置く）"] = [],
    ok: Annotated[str, "決めるボタンの文字"] = "OK",
    danger: Annotated[bool, "決めるボタンを、戻せない操作として赤く見せる"] = False,
    sticky: Annotated[bool, "欄が長いとき、ボタンの行を見えたままにする"] = False,
    initial: Annotated[dict, "初めの値（名前 → 値）"] = {},
    vars: Annotated[dict, "文の中の {名前} に入れる値・出し分けに使う値（画面が渡すもの）"] = {},
    values: Annotated[dict | None, "欄の今の値（読んだもの。欄の名前 → 値）"] = None,
    at: Annotated[list[str] | None, "values の中の、今の値のある場所（たどる名前の並び。空の名前があれば、今の値はないものとする）"] = None,
    also: Annotated[dict | None, "読んだ値（もう1つ。values にない道筋は、ここから探す）"] = None,
    rows: Annotated[list[dict], "読んだ一覧（options_from の source が rows の欄の選べるもの）"] = [],
    more: Annotated[list[dict], "読んだ一覧（options_from の source が more の欄の選べるもの）"] = [],
    problem: Annotated[str, "実行できなかった理由（窓の中に出す。入れた値は残る）"] = "",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_submitted(values: Annotated[dict[str, Any], "欄の名前 → 値（出ている欄だけ）"]) -> None: ...


def on_action(name: Annotated[str, "押したボタン（actions の name）"], values: Annotated[dict[str, Any], "欄の名前 → 値（出ている欄だけ）"] = {}) -> None: ...


def on_cancelled() -> None: ...
