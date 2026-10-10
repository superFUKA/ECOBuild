from typing import Annotated

from ..._output import run_command, usage_error


def command(
    *title: Annotated[str, "ボードの題名（既定：<リポジトリ名> タスク）"],
    owner: Annotated[str, "ボードの所有者（ユーザー・組織。既定はこのリポジトリの所有者）"] = "",
    sprint_start: Annotated[str, "最初のスプリントの開始日（YYYY-MM-DD。既定は今週の月曜日）"] = "",
    sprint_days: Annotated[int, "スプリントの日数"] = 14,
    sprints: Annotated[int, "最初に用意するスプリントの数"] = 3,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """このリポジトリ専用の標準のボードを作り、リポジトリにリンクします（Status：Backlog・Todo・In Progress・
    In Review・Done、Priority、Due、Estimate、Sprint、Planned Start、Planned End、Started）。

    作ったら、作業空間で ecobuild board use <URL> でこのモジュールにつなぎます。
    """
    if len(title) > 1:
        return usage_error("題名は1つだけ指定してください（空白を含むなら \"\" で囲みます）。", json)

    def render(r):
        fields = ", ".join(f.name for f in r.fields if f.type in ("SINGLE_SELECT", "NUMBER", "DATE", "ITERATION"))
        return (f"ボード {r.title} を作りました：{r.url}\n  フィールド：{fields}\n"
                f"つなぐには、作業空間で ecobuild board use {r.url}")

    return run_command("board create",
                       lambda inv: inv.module.create_board(title[0] if title else None, owner=owner or None, sprint_start=sprint_start or None,
                                                           sprint_days=sprint_days, sprints=sprints),
                       render, json_output=json)
