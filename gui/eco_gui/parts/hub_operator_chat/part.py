"""オペレーターとの会話。状態の印（待機中・考え中 など）、自分とオペレーターの吹き出し（`コード`と**太字**）、
返答ごとの「実行したコマンド（N）」、返答を待っている間の「考え中…」と「実行中：<コマンド>」、オペレーターが出した選択肢の箱。

会話の中身と状態は ecobuild gui conversation の答え。ここは並べて見せるだけ（送るのは部品 hub-operator-input）。
"""
from typing import Annotated, Literal


def part(
    conversation: Annotated[dict, "会話の記録と状態（messages：[{role: user|agent|system, text, ok, actions: [{command, ok}]}]、"
                                  "state：idle・thinking・starting・waiting・choice・exited・none、doing：実行中の道具、"
                                  "queued：待たせている発言の数、choice：{question, choice}、screen：起動中の画面の最後の数行、"
                                  "starting_for：起動を待っている秒数）"] = {},
    asked: Annotated[str | None, "送って、返答を待っている文（なければ null）"] = None,
    doing: Annotated[list[str], "返答を待っている間に、オペレーターが使い始めた道具（続いて届く。最後のものを「実行中：」に出す）"] = [],
    failed: Annotated[str | None, "送れなかった・返答を受け取れなかった理由（なければ null）"] = None,
    intro: Annotated[str, "会話が始まる前に、真ん中に出す紹介の文"] = "",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_key(key: Annotated[Literal["up", "down", "enter", "esc"], "選択肢の箱で押したキー（↑・↓・決定・取り消す）"]) -> None: ...


def on_show() -> None:
    """起動中のままのとき：オペレーターの画面を開いて確かめる。"""
