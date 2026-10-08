from typing import Annotated

from ..._output import run_command
from .show import render


def command(
    url: Annotated[str, "ボードのURL（https://github.com/users/<所有者>/projects/<番号>）"],
    status_field: Annotated[str, "状態を表す単一選択のフィールド"] = "Status",
    todo: Annotated[str, "未着手に当てる選択肢（既定：Todo 等を探す）"] = "",
    in_progress: Annotated[str, "作業中に当てる選択肢（既定：In Progress 等）"] = "",
    in_review: Annotated[str, "レビュー待ちに当てる選択肢（既定：In Review 等。なければ作業中と同じ）"] = "",
    done: Annotated[str, "完了に当てる選択肢（既定：Done 等）"] = "",
    priority_field: Annotated[str, "優先度の項目（単一選択。既定：Priority）"] = "",
    due_field: Annotated[str, "期限の項目（日付。既定：Due、日付の項目が1つならそれ）"] = "",
    estimate_field: Annotated[str, "見積もりの項目（数値。既定：Estimate、数値の項目が1つならそれ）"] = "",
    sprint_field: Annotated[str, "スプリントの項目（イテレーション。既定：Sprint、1つならそれ）"] = "",
    shared: Annotated[bool, "他のリポジトリと共有するボードでもつなぐ（既定はこのリポジトリ専用だけ）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """このモジュールのタスクをボードにつなぎます（ecobuild.toml の [board]。作業空間で行い、PRで反映します）。"""
    stages = {"todo": todo, "in_progress": in_progress, "in_review": in_review, "done": done}
    schema = {"priority": priority_field, "due": due_field, "estimate": estimate_field, "sprint": sprint_field}
    return run_command("board use", lambda inv: inv.module.use_board(url, status_field=status_field, stages=stages,
                                                                      schema=schema, shared=shared),
                       lambda r: render(r) + "\necobuild.toml を変えました。task commit と task submit で反映してください。"
                                             "\n今あるタスクは ecobuild board sync でボードに加えられます。",
                       json_output=json)
