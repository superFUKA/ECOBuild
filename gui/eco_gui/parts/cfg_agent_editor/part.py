"""エージェントの設定。左に一覧（全エージェント共通 → 役 → スキル）、右に選んだものを、そのままの欄で直す。

役：基本（表示名・モデル）・起動・文書・最初の発言・改善のループ・渡すツール・使えるスキル・起動してよい子。
直したところがあるときだけ「保存」「元に戻す」を押せる。保存は、変えた項目だけを出す（何を変えるかは、この部品は
知らない。受けた側がコマンドに渡す）。渡すツールを選ぶたびに、その並びを出す（tools_changed）。多すぎないか・
この役より強い子はどれかは、届いた確かめ（fit）のとおりに見せる（この部品では決めない）。
"""
from typing import Annotated, Literal


def part(
    agents: Annotated[list[dict], "役の一覧（{name, title, source, human_start, model, tools, pending}）"] = [],
    skills: Annotated[list[dict], "スキルの一覧（{name, description, pending}）"] = [],
    tools: Annotated[list[dict], "渡せるツールの一覧（{name, mark, summary, area}）"] = [],
    presets: Annotated[list[dict], "プリセットの一覧（{name, source}。見本と同じ名前の役は「消す」が「プリセットに戻す」になる）"] = [],
    rules: Annotated[dict | None, "全エージェント共通の文（{common, in_force, pending, root}）"] = None,
    registration: Annotated[dict | None, "選んだ役の中身（一覧の項目と document・first_prompt 等）"] = None,
    skill: Annotated[dict | None, "選んだスキルの中身（{name, description, document, used_by, files, folder, pending}）"] = None,
    fit: Annotated[dict | None, "選んだツールの確かめ（{name, tools, count, total, owner, limit, too_many, stronger, parents}）"] = None,
    select: Annotated[dict | None, "選ぶもの（{kind: common・role・skill, name}。変わって届いたときに、それを選ぶ）"] = None,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_selected(kind: Annotated[Literal["common", "role", "skill"], "選んだものの種類"],
                name: Annotated[str, "役・スキルの名前（共通の文なら空）"] = "") -> None:
    if kind != "common" and not name:
        raise ValueError("名前が要ります")


def on_add() -> None: ...


def on_add_skill() -> None: ...


def on_tools_changed(name: Annotated[str, "役の名前"],
                     text: Annotated[str, "今選んでいるツールの並び（カンマ区切り。1つもなければ「,」）"]) -> None: ...


def on_save(name: Annotated[str, "役の名前"],
            title: Annotated[str | None, "表示名（変えたときだけ）"] = None,
            model: Annotated[str | None, "モデル（変えたときだけ。既定に戻すなら空白1つ）"] = None,
            human_start: Annotated[bool | None, "人が手で起動できるか（変えたときだけ）"] = None,
            tools: Annotated[str | None, "渡すツール（変えたときだけ。カンマ区切り。1つもなければ「,」）"] = None,
            skills: Annotated[str | None, "使えるスキル（変えたときだけ。カンマ区切り。1つもなければ「,」）"] = None,
            children: Annotated[str | None, "起動してよい子（変えたときだけ。カンマ区切り。1つもなければ「,」）"] = None,
            max_children: Annotated[int | None, "同時に持てる子の数（変えたときだけ）"] = None,
            first_prompt: Annotated[str | None, "最初の発言（変えたときだけ。空にするなら空白1つ）"] = None,
            evaluation: Annotated[str | None, "評価のしかた（変えたときだけ。空にするなら空白1つ）"] = None,
            lessons: Annotated[str | None, "教訓の記録先（変えたときだけ。空にするなら空白1つ）"] = None,
            max_rounds: Annotated[int | None, "評価し直す回数の上限（変えたときだけ）"] = None,
            max_turns: Annotated[int | None, "ターン数の上限（変えたときだけ）"] = None,
            max_cost: Annotated[float | None, "費用の上限（変えたときだけ）"] = None,
            document: Annotated[str | None, "文書（変えたときだけ）"] = None) -> None:
    if not name:
        raise ValueError("役の名前が要ります")


def on_remove(name: Annotated[str, "消す（プリセットに戻す）役の名前"]) -> None:
    if not name:
        raise ValueError("役の名前が要ります")


def on_to_preset(name: Annotated[str, "このPCのプリセットにする役の名前"]) -> None:
    if not name:
        raise ValueError("役の名前が要ります")


def on_save_skill(name: Annotated[str, "スキルの名前"],
                  description: Annotated[str | None, "説明（変えたときだけ）"] = None,
                  document: Annotated[str | None, "本文（変えたときだけ）"] = None) -> None:
    if not name:
        raise ValueError("スキルの名前が要ります")


def on_remove_skill(name: Annotated[str, "消すスキルの名前"]) -> None:
    if not name:
        raise ValueError("スキルの名前が要ります")


def on_skill_to_preset(name: Annotated[str, "このPCのスキルにするスキルの名前"]) -> None:
    if not name:
        raise ValueError("スキルの名前が要ります")


def on_save_rules(common: Annotated[str, "全エージェント共通の文（空なら消す）"]) -> None: ...
