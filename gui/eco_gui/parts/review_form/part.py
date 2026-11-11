"""提出まわりの入力の窓の中身：取り込む・完了にする・承認して取り込む・差し戻す・反映・コメント・提出・ブランチの提出の取り込み。

上に「何が起きるか」の表（タスクを完了するかどうかで、文が変わる）、下に入力欄と、実行・やめるのボタン。
入れた値は submitted でまとめて出す（どのコマンドを呼ぶかは、画面のつなぎが kind で決める）。
"""
from typing import Annotated, Literal


def part(
    kind: Annotated[Literal["finish", "complete", "approve", "reject", "apply", "comment", "submit", "merge"], "どの入力の窓か"],
    id: Annotated[str, "タスクの番号（merge なら、ブランチの名前。submit なら空でよい）"] = "",
    base: Annotated[str, "取り込み先（作成元）のブランチ"] = "",
    partial: Annotated[bool, "中間提出か（「タスクを完了する」の初めの値が外れる）"] = False,
    submitted: Annotated[bool, "もう提出しているか（complete・submit の説明が変わる）"] = False,
) -> None: ...


def on_submitted(
    kind: Annotated[str, "どの入力の窓か"],
    id: Annotated[str, "タスクの番号・ブランチの名前"] = "",
    message: Annotated[str, "コメント・直してほしいこと"] = "",
    subject: Annotated[str, "取り込むコミットの件名"] = "",
    title: Annotated[str, "提出の題名"] = "",
    reviewer: Annotated[str, "見てもらう人（カンマ区切り）"] = "",
    ignore_checks: Annotated[bool, "CI が失敗していても取り込む"] = False,
    draft: Annotated[bool, "下書きで提出する"] = False,
    complete: Annotated[bool, "タスクを完了する"] = False,
    partial: Annotated[bool, "タスクを続ける（complete の逆）"] = False,
) -> None:
    if kind in ("reject", "comment") and not message.strip():
        raise ValueError("内容を書いてください")


def on_cancelled() -> None: ...
