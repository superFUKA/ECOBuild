from typing import Annotated

from ..._output import lines, run_command

STAGE_NAMES = {"todo": "未着手", "in_progress": "作業中", "in_review": "レビュー待ち", "done": "完了"}


def render(r):
    return lines(
        f"ボード：{r.title}  {r.url}",
        f"状態のフィールド：{r.status_field}",
        "作業の段階に当てた選択肢：" + "、".join(f"{STAGE_NAMES[s]}＝{name}" for s, name in r.stages.items() if name),
        "フィールド：\n" + "\n".join(
            f"  {f.name}（{f.type}）" + (f"：{', '.join(o.name for o in f.options)}" if f.options else "")
            for f in r.fields if f.type in ("TEXT", "NUMBER", "DATE", "SINGLE_SELECT", "ITERATION")),
    )


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """つないでいるボードと、そのフィールド（型・選択肢）、作業の段階に当てた選択肢を表示します。"""
    return run_command("board show", lambda inv: inv.module.board_status(), render, json_output=json)
