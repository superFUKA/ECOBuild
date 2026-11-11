"""作業空間の窓の下端のステータスバー。左に「出力」（最後の実行の状態）、右に作業空間の状況。

「↑ 未Push N／Push済み」「↓ <作成元> より N 遅れ・衝突 N」「HH:MM に確認／未確認」（押すと GitHub の最新を確かめる）。"""
from typing import Annotated, Literal


def part(
    status: Annotated[dict, "状態（ecobuild status：task・reviewing・ahead・base）"] = {},
    remote: Annotated[dict, "GitHub の最新を確かめた状態（ecobuild status --fetch：base_behind・base_conflicts）"] = {},
    run: Annotated[Literal["", "run", "ok", "bad"] | None, "最後の実行の状態（実行中・成功・失敗）"] = "",
    kind: Annotated[str | None, "最後に動かしたものの種類（test・run・check なら、結果から失敗を読む）"] = "",
    result: Annotated[dict | None, "最後の実行の結果（試験の失敗の数・終了コード・確認の項目）"] = None,
    output_hidden: Annotated[bool | None, "出力欄を隠しているか"] = False,
) -> None: ...


def on_action(name: Annotated[str, "押したもの（fetch・show_output・hide_output）"]) -> None:
    if name not in ("fetch", "show_output", "hide_output"):
        raise ValueError("操作の名前が違います")
