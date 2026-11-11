"""入力の窓（フォーム）。題・説明・欄の並び・「やめる」と決めるボタン。決めると、全部の欄の値をまとめて出す。

欄（fields）の1つは {name, label, type, …}：
- type：text（1行）・select（1つ選ぶ）・checks（いくつか選ぶ）・toggle（する・しない）・note（説明の文だけ）
- placeholder・hint（下に小さく出す文）・required（空では決められない）
- select・checks の選べるもの：options（[{value, label}]）か、source（"rows"・"more"：読んだ一覧）＋ value_key・label_key・
  note_key（横に小さく）・where（{項目: 値}：合う行だけ）・none_label（select の「選ばない」）
- checks の join：出す値を、この文字でつないだ1つの文字にする（コマンドがカンマ区切りで受けるとき）。empty は1つも選ばないときの値
- toggle の on・off：出す値（書かなければ真偽）
初めの値は initial（名前 → 値。checks は並びか、join でつないだ文字）。打った値は、この部品の中に持つ。
"""
from typing import Annotated


def part(
    fields: Annotated[list[dict], "欄の並び"],
    title: Annotated[str, "題"] = "",
    intro: Annotated[str, "説明"] = "",
    initial: Annotated[dict, "初めの値（名前 → 値）"] = {},
    rows: Annotated[list[dict], "読んだ一覧（source が rows の欄の選べるもの）"] = [],
    more: Annotated[list[dict], "読んだ一覧（source が more の欄の選べるもの）"] = [],
    ok: Annotated[str, "決めるボタンの文字"] = "決める",
    danger: Annotated[bool, "決めるボタンを、戻せない操作として赤く見せる"] = False,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_submitted(values: Annotated[dict, "全部の欄の値（名前 → 値）"]) -> None: ...


def on_cancelled() -> None: ...
