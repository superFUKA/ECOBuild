from typing import Annotated

from ..._output import lines, run_command


def command(
    dry_run: Annotated[bool, "変えずに、変える内容だけを表示する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ボードを実際の状態に合わせます：開いているタスクをボードに加え、状態を作業の段階（Issue・PR・作業空間）に合わせます。

    計画の段階（作業の段階に当てていない選択肢）と、作業空間のない作業中のタスクはそのままにします。
    """

    def render(r):
        verb = "加えます" if r.dry_run else "加えました"
        return lines(
            f"ボードに{verb}：" + ", ".join(f"#{n}" for n in r.added) if r.added else None,
            "\n".join(f"#{c.number} {c.title}：{c.before or '（なし）'} → {c.after}" for c in r.changed) or None,
        ) or "ボードは実際の状態と合っています"

    return run_command("board sync", lambda inv: inv.module.sync_board(dry_run=dry_run), render, json_output=json)
