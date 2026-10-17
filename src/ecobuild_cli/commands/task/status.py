import datetime
from typing import Annotated

from ..._output import lines, optional_argument, run_command
from ._show import STAGE_NAMES, dates_text, elsewhere, plan_text, submission_text

MERGEABLE = {"CONFLICTING": "衝突あり（ecobuild sync で解決）", "MERGEABLE": "可能"}


def refs(label, tasks):
    """親子・依存の相手の一覧（なければ表示しない）。"""
    if not tasks:
        return None
    return f"{label}：\n" + "\n".join(f"  #{t.number} {t.title}" + ("（閉じています）" if t.state == "closed" else "")
                                      for t in tasks)


def submission(r) -> str:
    """提出の行。中間提出を取り込んだ後（タスクは開いたまま）は、前回の中間提出と、今の提出がないことを分けて出す。"""
    pr = r.pull_request
    if pr is None:
        return "提出：なし"
    if pr.state == "merged" and r.state == "open":
        return f"提出：なし（前回の中間提出は取り込み済み {pr.url}）"
    return f"提出：{submission_text(pr)} {pr.url}"


def command(
    *number: Annotated[int, "Issueの番号（--issue と同じ）"],
    issue: Annotated[int, "Issueの番号（既定：今いるタスクブランチ）"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクの状態：Issue（ラベル・担当者・コメント）、タスクブランチ、提出（レビュー・コメント・CIの結果）を表示します。"""

    issue = optional_argument(number, issue, "--issue", json)

    def render(r):
        a = r.activity
        details = []
        if a is not None:
            details += [f"  CI {c.name}：{c.conclusion or c.status}" for c in a.checks]
            details += [f"  レビュー {v.author}：{v.state}" + (f"：{v.body}" if v.body else "") for v in a.reviews]
            details += [f"  コメント {c.author}：{c.body}" for c in a.comments]
        opened = r.pull_request is not None and r.pull_request.state == "open"
        return lines(
            f"#{r.number} {r.title}（{'開いています' if r.state == 'open' else '閉じています'}）{r.url}",
            f"ラベル：{', '.join(r.labels)}" if r.labels else None,
            f"担当者：{', '.join(r.assignees)}" if r.assignees else "担当者：なし",
            f"マイルストーン：{r.milestone}" if r.milestone else None,
            f"段階：{STAGE_NAMES[r.task.stage]}" if r.task is not None and r.task.stage in STAGE_NAMES else None,
            f"計画：{plan_text(r.task)}" if r.task is not None and plan_text(r.task) else None,
            f"日付：{dates_text(r.task)}" if r.task is not None and dates_text(r.task) else None,
            "期限切れです" if r.task is not None and r.state == "open" and r.task.due is not None
            and r.task.due < datetime.date.today() else None,
            f"親タスク：#{r.parent.number} {r.parent.title}" if r.parent else None,
            refs("子タスク", r.subtasks), refs("先に終わるべきタスク", r.blocked_by),
            refs("このタスクを待っているタスク", r.blocking),
            "Issueのコメント：\n" + "\n".join(f"  {c.author}：{c.body}" for c in r.comments) if r.comments else None,
            f"タスクブランチ：task/{r.number}（作成元 {r.base}）{elsewhere(r.workspace, here[0])}"
            if r.task_branch or r.workspace
            else f"タスクブランチ：GitHubにだけあります（ecobuild task start {r.number} で再開）" if r.remote
            else "タスクブランチ：なし",
            submission(r),
            f"  取り込み：{MERGEABLE.get(a.mergeable, '確認中')}" if a is not None and opened else None,
            "\n".join(details) or None,
        )

    here = []

    def status(inv):
        here.append(inv.module.root)
        return inv.module.task_status(issue or None)

    return run_command("task status", status, render, json_output=json)
