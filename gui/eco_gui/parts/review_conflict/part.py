"""衝突を直す。衝突したファイルの一覧と、選んだファイルの衝突の箇所（今の側・入ってくる側を左右に並べる）。

箇所ごとに側を選ぶと、下の結果が変わる。結果は手でも直せる。保存（saved）・ファイル全体を片方の側に（taken）・TortoiseGit で直す（tortoise）・
全部直したら続ける（continued）・やめる（aborted）を出す。選んだ側・直している途中の文字は、この部品の中だけにある。
"""
from typing import Annotated, Literal


def part(
    data: Annotated[dict | None, "衝突したファイルと箇所（sync conflicts の結果：stopped・current・incoming・ready・files）"] = None,
    status: Annotated[dict | None, "作業空間の状態（status の結果。ブランチの名前を出す）"] = None,
    first: Annotated[str | None, "初めに出すファイル（右クリックしたファイル。なければ先頭）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_saved(path: Annotated[str, "保存するファイル"], text: Annotated[str, "直した中身"]) -> None:
    if not path:
        raise ValueError("ファイルが要ります")


def on_taken(paths: Annotated[list[str], "片方の側にするファイル（空なら、衝突したファイル全部）"],
             side: Annotated[Literal["current", "incoming"], "採る側"]) -> None: ...


def on_tortoise(path: Annotated[str, "TortoiseGit で直すファイル"]) -> None:
    if not path:
        raise ValueError("ファイルが要ります")


def on_continued() -> None: ...


def on_aborted() -> None: ...
