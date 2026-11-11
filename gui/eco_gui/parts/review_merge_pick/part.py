"""ブランチ同士の取り込みの、向きと相手を選ぶ所。カードの見出し（畳める。右に、下見の要約）と、
「取り込むブランチ → 取り込み先」の行（片方は選んでいるブランチで固定、もう片方をセレクトで選ぶ。→ で向きを入れ替える。「確かめ直す」）。

見せ方だけ：GitHub にないブランチはセレクトで選べない（灰色）。初めの相手（このブランチから作ったもの、なければ作成元、なければほか）を
選んで出す。取り込めるか・何が起きるかは決めない（下見は ecobuild が答える）。
"""
from typing import Annotated


def part(
    branches: Annotated[list[dict], "ブランチ（branch list の行。タスクブランチも届いてよい。共有ブランチだけを使う）"] = [],
    name: Annotated[str | None, "選んでいるブランチ（固定の側）。空なら既定のブランチ"] = None,
    default_base: Annotated[str | None, "既定のブランチ（選んでいないときの固定の側）"] = None,
    side: Annotated[str, "初めに、選んでいるブランチを置く側：into（取り込み先）か from（取り込むブランチ）"] = "into",
    source: Annotated[str | None, "今の、取り込むブランチ"] = None,
    into: Annotated[str | None, "今の、取り込み先"] = None,
    plan: Annotated[dict | None, "下見の結果（見出しの要約に使う：name・into・method・commit_count）"] = None,
    open: Annotated[bool | None, "カードを開けているか"] = None,
    foldable: Annotated[bool, "畳めるカードにする（偽なら、いつも開けておく）"] = True,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_changed(
    source: Annotated[str, "取り込むブランチ"],
    into: Annotated[str, "取り込み先"],
) -> None:
    if not source or not into or source == into:
        raise ValueError("取り込むブランチと取り込み先は、別のブランチを選びます")


def on_toggled(open: Annotated[bool, "カードを開けたか"]) -> None: ...


def on_reload() -> None: ...
