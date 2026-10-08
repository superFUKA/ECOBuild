from typing import Annotated

from ..._output import optional_argument, run_command, split_list, usage_error


def command(
    *number: Annotated[int, "PRの番号（--pr と同じ）"],
    pr: Annotated[int, "PRの番号（既定：今いる作業空間のPR）"] = 0,
    title: Annotated[str, "新しい題名"] = "",
    body: Annotated[str, "新しい本文（作業空間のPRでは、Issueとのつながり Closes／Refs #<番号> は残ります）"] = "",
    clear_body: Annotated[bool, "本文を消す（作業空間のPRでは、Issueとのつながりの行だけを残します）"] = False,
    base: Annotated[str, "新しい向き先のブランチ（作業空間のPRなら、作業空間の作成元も変わります）"] = "",
    add_reviewer: Annotated[str, "レビューを頼む人（カンマ区切り）"] = "",
    remove_reviewer: Annotated[str, "レビューの依頼を外す人（カンマ区切り）"] = "",
    add_label: Annotated[str, "付けるラベル（カンマ区切り。なければ作る）"] = "",
    remove_label: Annotated[str, "外すラベル（カンマ区切り）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """PRの題名・本文・向き先・レビュアー・ラベルを変えます。"""
    pr = optional_argument(number, pr, "--pr", json)
    if body and clear_body:
        return usage_error("--body と --clear-body の両方は指定できません。", json)

    def action(inv):
        return inv.module.edit_pull_request(
            pr or None, title=title or None, body="" if clear_body else (body or None), base=base or None,
            add_reviewers=split_list(add_reviewer), remove_reviewers=split_list(remove_reviewer),
            add_labels=split_list(add_label), remove_labels=split_list(remove_label))

    return run_command("pr edit", action, lambda r: f"PR #{r.number} {r.title} を更新しました（{r.head} → {r.base}）",
                       json_output=json)
