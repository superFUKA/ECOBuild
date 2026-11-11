"""タスク管理の上の帯。表示のタブ（ボード・一覧・次にやる・日程・スプリント・概要）と、絞り込み（検索・担当者・スプリント・マイルストーン・着手できる・完了・削除）。

絞り込みは見せ方：選んだ値を出すだけで、絞るのは表示の部品（changed）。読み直しの要る印（着手できる・完了・削除）を変えたときは、
今の表示を開き直す形（view）で出す。
"""
from typing import Annotated, Literal


def part(
    view: Annotated[str, "今の表示（画面の名前：board・tasks・task-next・schedule・task-sprint・task-summary）"],
    tasks: Annotated[list[dict], "タスク（担当者の候補にする）"] = [],
    sprints: Annotated[list[dict], "スプリント（{name, start, end}）"] = [],
    milestones: Annotated[list[dict], "マイルストーン（{title}）"] = [],
    me: Annotated[str, "自分のアカウント"] = "",
    start: Annotated[dict, "開いたときの絞り込み（{search, assignee, sprint, milestone, ready, closed, deleted}）"] = {},
    scope: Annotated[Literal["all", "assignee", "none"], "この表示に当たる絞り込み（all：全部、assignee：担当者だけ、none：出さない）"] = "all",
) -> None: ...


def _check(filter: dict) -> None:
    for name in ("search", "assignee", "sprint", "milestone"):
        if not isinstance(filter.get(name, ""), str):
            raise ValueError("絞り込みの値は文字にしてください")


def on_view(
    id: Annotated[str, "開く表示（画面の名前。今の表示のままなら、読み直しの要る印を変えたとき）"],
    filter: Annotated[dict, "絞り込み（{search, assignee（@me は自分、- は担当なし）, sprint（current は今のスプリント、- はなし）, milestone, ready, closed, deleted}）"] = {},
    all: Annotated[bool, "閉じたタスクも読む（完了か削除を出すとき）"] = False,
    ready: Annotated[bool, "着手できるものだけを読む"] = False,
) -> None:
    if not id:
        raise ValueError("表示の名前が要ります")
    _check(filter)


def on_changed(filter: Annotated[dict, "絞り込み（読み直しの要らない値を変えたとき。view と同じ形）"] = {}) -> None:
    _check(filter)
