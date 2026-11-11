"""ブランチ同士の取り込みの、事前確認のカード。取り込む前に、何が起きるかを見せる（ecobuild branch merge <名前> --into <先> --dry-run の結果）。

方式の印（早送り・マージコミット＝緑、衝突する＝赤、取り込み済み）、入るコミットの数と一覧、変わるファイル、衝突するファイルの赤い帯、
取り込める人。見せるだけで、できるかどうかは決めない（方式・衝突・取り込める人は、ecobuild が答えたもの）。
"""
from typing import Annotated


def part(
    plan: Annotated[dict | None, "下見の結果（name・into・method・commits・commit_count・files・file_count・conflicts・resolved・allowed・owners）。まだなら null"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "確かめられなかった理由"] = "",
) -> None: ...
