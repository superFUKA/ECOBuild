"""ECOBuild の新しい版があるかの知らせ。一覧の上の帯（新しい版があるときだけ出す）か、設定の中の1行（最新のときも出す）。"""
from typing import Annotated, Literal


def part(
    check: Annotated[dict | None, "確かめた結果（{current, latest, ref, up_to_date, gui}）。まだなら null"] = None,
    look: Annotated[Literal["banner", "status"], "見せ方：banner（上の帯。新しい版があるときだけ）・status（設定の中の1行）"] = "banner",
    loading: Annotated[bool, "確かめている最中"] = False,
    error: Annotated[str, "確かめられなかった理由（手元のソースから入れた等。帯では何も出さない）"] = "",
) -> None: ...


def on_pressed() -> None: ...
