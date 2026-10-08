from typing import Annotated

from ecotask.model import ROLE_NAMES

from ..._output import lines, run_command

STAGE_NAMES = {"todo": "未着手", "in_progress": "作業中", "in_review": "レビュー待ち", "done": "完了"}


def scope_text(scope) -> str:
    items = "、".join(f"{name or '下書き'} {count}" for name, count in sorted(scope.items.items())) or "なし"
    return (f"リポジトリ：{scope.repository}（{'非公開' if scope.repository_private else '公開'}）"
            f"  ボード：{'公開' if scope.public else '非公開'}{'・共有' if scope.shared else '・専用'}\n"
            f"リンク：{', '.join(scope.linked) or 'なし'}\n項目のリポジトリ：{items}")


def render(r):
    return lines(
        f"ボード：{r.title}  {r.url}",
        f"状態のフィールド：{r.status_field}",
        "作業の段階に当てた選択肢：" + "、".join(f"{STAGE_NAMES[s]}＝{name}" for s, name in r.stages.items() if name),
        "計画の値に当てた項目：" + ("、".join(f"{ROLE_NAMES[role]}＝{name}" for role, name in r.schema.items())
                                 or "なし（task plan・task next 等の判断は使えません）"),
        scope_text(r.scope) if r.scope is not None else None,
        "フィールド：\n" + "\n".join(
            f"  {f.name}（{f.type}）" + (f"：{', '.join(o.name for o in f.options)}" if f.options else "")
            for f in r.fields if f.type in ("TEXT", "NUMBER", "DATE", "SINGLE_SELECT", "ITERATION")),
    )


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """つないでいるボードと、そのフィールド（型・選択肢）、作業の段階に当てた選択肢を表示します。"""
    return run_command("board show", lambda inv: inv.module.board_status(), render, json_output=json)
