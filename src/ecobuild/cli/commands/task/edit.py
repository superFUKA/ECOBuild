from typing import Annotated

from ....errors import EcoBuildError, ErrorCode
from ..._output import lines, run_command, split_list, split_numbers

DATES = ("due", "planned_start", "planned_end")


def _dates(text: str) -> tuple[str, ...]:
    """--clear-date の値（期限・予定日だけ。優先度等は task plan --clear で消す）。"""
    names = split_list(text)
    unknown = [name for name in names if name not in DATES]
    if unknown:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"消す日付 {', '.join(unknown)} はありません。",
                            hint=f"{'・'.join(DATES)} から選んでください。")
    return names


def command(
    issue: Annotated[int, "Issueの番号"],
    title: Annotated[str, "新しい題名"] = "",
    body: Annotated[str, "新しい本文"] = "",
    add_label: Annotated[str, "付けるラベル（カンマ区切り。なければ作る）"] = "",
    remove_label: Annotated[str, "外すラベル（カンマ区切り）"] = "",
    add_assignee: Annotated[str, "加える担当者（カンマ区切り。@me は自分）"] = "",
    remove_assignee: Annotated[str, "外す担当者（カンマ区切り。@me は自分）"] = "",
    parent: Annotated[int, "親タスクの番号（既に別の親があれば、先に --clear-parent）"] = 0,
    clear_parent: Annotated[bool, "親タスクから外す"] = False,
    add_blocked_by: Annotated[str, "先に終わるべきタスクを加える（カンマ区切りの番号）"] = "",
    remove_blocked_by: Annotated[str, "先に終わるべきタスクから外す（カンマ区切りの番号）"] = "",
    milestone: Annotated[str, "マイルストーンの題名"] = "",
    clear_milestone: Annotated[bool, "マイルストーンから外す"] = False,
    due: Annotated[str, "期限（YYYY-MM-DD）"] = "",
    planned_start: Annotated[str, "開始予定日（YYYY-MM-DD）"] = "",
    planned_end: Annotated[str, "終了予定日（YYYY-MM-DD）"] = "",
    clear_date: Annotated[str, "消す日付（カンマ区切り：due・planned_start・planned_end）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（Issue）の題名・本文・ラベル・担当者・親タスク・依存・マイルストーン・期限・予定日を変えます。"""
    add_blockers = split_numbers(add_blocked_by, "--add-blocked-by", json)
    remove_blockers = split_numbers(remove_blocked_by, "--remove-blocked-by", json)

    def action(inv):
        return inv.module.edit_task(issue, title=title or None, body=body or None,
                                    add_labels=split_list(add_label), remove_labels=split_list(remove_label),
                                    add_assignees=split_list(add_assignee),
                                    remove_assignees=split_list(remove_assignee), parent=parent or None,
                                    clear_parent=clear_parent, add_blocked_by=add_blockers,
                                    remove_blocked_by=remove_blockers, milestone=milestone or None,
                                    clear_milestone=clear_milestone,
                                    plan={"due": due or None, "planned_start": planned_start or None,
                                          "planned_end": planned_end or None}, clear_plan=_dates(clear_date))

    def render(r):
        return lines(f"#{r.number} {r.title} を更新しました",
                     f"  ラベル：{', '.join(r.labels)}" if r.labels else None,
                     f"  担当者：{', '.join(r.assignees)}" if r.assignees else None,
                     f"  マイルストーン：{r.milestone}" if r.milestone else None)

    return run_command("task edit", action, render, json_output=json)
