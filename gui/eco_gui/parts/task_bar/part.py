"""タスク管理の上の帯。表示のタブ（ボード・一覧・次にやる・日程・スプリント・概要）と、絞り込み（検索・担当者・スプリント・マイルストーン・着手できる・完了・削除）。

絞り込みは見せ方：選んだ値を出すだけで、絞るのは表示の部品。読み直しの要る印（着手できる・完了・削除）は reload で出す。
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


def _check(assignee: str, sprint: str, milestone: str) -> None:
    for value in (assignee, sprint, milestone):
        if not isinstance(value, str):
            raise ValueError("絞り込みの値は文字にしてください")


def on_view(
    id: Annotated[str, "選んだ表示（画面の名前）"],
    search: Annotated[str, "検索の文字"] = "", assignee: Annotated[str, "担当者（@me は自分、- は担当なし）"] = "",
    sprint: Annotated[str, "スプリント（current は今のスプリント、- はなし）"] = "", milestone: Annotated[str, "マイルストーン（- はなし）"] = "",
    ready: Annotated[bool, "着手できるものだけ"] = False, closed: Annotated[bool, "完了したタスクも"] = False,
    deleted: Annotated[bool, "削除したタスクも"] = False, all: Annotated[bool, "閉じたタスクも読む（完了か削除を出すとき）"] = False,
) -> None:
    if not id:
        raise ValueError("表示の名前が要ります")
    _check(assignee, sprint, milestone)


def on_changed(
    search: Annotated[str, "検索の文字"] = "", assignee: Annotated[str, "担当者"] = "",
    sprint: Annotated[str, "スプリント"] = "", milestone: Annotated[str, "マイルストーン"] = "",
    ready: Annotated[bool, "着手できるものだけ"] = False, closed: Annotated[bool, "完了したタスクも"] = False,
    deleted: Annotated[bool, "削除したタスクも"] = False, all: Annotated[bool, "閉じたタスクも読む"] = False,
) -> None:
    _check(assignee, sprint, milestone)


def on_reload(
    search: Annotated[str, "検索の文字"] = "", assignee: Annotated[str, "担当者"] = "",
    sprint: Annotated[str, "スプリント"] = "", milestone: Annotated[str, "マイルストーン"] = "",
    ready: Annotated[bool, "着手できるものだけ"] = False, closed: Annotated[bool, "完了したタスクも"] = False,
    deleted: Annotated[bool, "削除したタスクも"] = False, all: Annotated[bool, "閉じたタスクも読む"] = False,
) -> None:
    _check(assignee, sprint, milestone)
