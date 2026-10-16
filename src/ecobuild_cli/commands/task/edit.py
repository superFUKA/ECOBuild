from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ..._output import lines, run_command, split_list, split_numbers
from ._show import STAGE_NAMES, plan_text

DATES = ("due", "planned_start", "planned_end")
VALUES = ("priority", "estimate", "sprint") + DATES


def _cleared(text: str) -> tuple[str, ...]:
    names = split_list(text)
    unknown = [name for name in names if name not in VALUES]
    if unknown:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"消す値 {', '.join(unknown)} はありません。",
                            hint=f"{'・'.join(VALUES)} から選んでください（カンマ区切り）。")
    return names


def command(
    issue: Annotated[int, "タスクの番号"],
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
    priority: Annotated[str, "優先度（High・Middle・Low）"] = "",
    due: Annotated[str, "期限（YYYY-MM-DD）"] = "",
    estimate: Annotated[str, "見積もり（数値）"] = "",
    sprint: Annotated[str, "スプリント（名前か current）"] = "",
    planned_start: Annotated[str, "開始予定日（YYYY-MM-DD）"] = "",
    planned_end: Annotated[str, "終了予定日（YYYY-MM-DD）"] = "",
    stage: Annotated[str, "作業を始める前の段階（planned：計画中、todo：未着手）"] = "",
    clear: Annotated[str, "消す計画の値（カンマ区切り：priority・estimate・sprint・due・planned_start・planned_end）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクの題名・ラベル・担当者・計画の値などを変えます。

    変えられるのは、題名・本文・ラベル・担当者・親タスク・依存・マイルストーンと、計画の値（優先度・期限・見積もり・
    スプリント・予定日）・作業を始める前の段階です。
    """
    add_blockers = split_numbers(add_blocked_by, "--add-blocked-by", json)
    remove_blockers = split_numbers(remove_blocked_by, "--remove-blocked-by", json)

    def action(inv):
        module = inv.module
        cleared = _cleared(clear)
        issue_changes = dict(title=title or None, body=body or None, add_labels=split_list(add_label),
                             remove_labels=split_list(remove_label), add_assignees=split_list(add_assignee),
                             remove_assignees=split_list(remove_assignee), parent=parent or None,
                             clear_parent=clear_parent, add_blocked_by=add_blockers, remove_blocked_by=remove_blockers,
                             milestone=milestone or None, clear_milestone=clear_milestone)
        dates = {"due": due or None, "planned_start": planned_start or None, "planned_end": planned_end or None}
        plan = {"priority": priority or None, "estimate": estimate or None, "sprint": sprint or None}
        planned_clear = tuple(c for c in cleared if c not in DATES)
        dated_clear = tuple(c for c in cleared if c in DATES)
        changed = any(v for v in issue_changes.values()) or any(dates.values()) or dated_clear
        planned = any(plan.values()) or planned_clear or stage
        if not (changed or planned):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "変更する内容がありません。",
                                hint="ecobuild task edit --help で変えられる項目を確認できます。")
        if changed:
            module.repository.edit_task(issue, **issue_changes, plan=dates, clear_plan=dated_clear)
        if planned:
            module.repository.plan_task(issue, **plan, clear=planned_clear, stage=stage or None)
        return module.task_status(issue).task

    def render(r):
        stage_name = STAGE_NAMES.get(r.stage or "", "")
        return lines(f"#{r.number} {r.title} を更新しました" + (f"〈{stage_name}〉" if stage_name else ""),
                     f"  計画：{plan_text(r)}" if plan_text(r) else None,
                     f"  ラベル：{', '.join(r.labels)}" if r.labels else None,
                     f"  担当者：{', '.join(r.assignees)}" if r.assignees else None,
                     f"  マイルストーン：{r.milestone}" if r.milestone else None)

    return run_command("task edit", action, render, json_output=json)
