from typing import Annotated

from ..._output import run_command


def command(
    *paths: Annotated[str, "ステージするファイル"],
    all: Annotated[bool, "削除も含めて、すべての変更をステージする"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """変更をステージします（タスクブランチでのみ。上級者向け）。

    普段は不要です：ecobuild task commit は変更をすべて（パスを書けばそれだけ）含め、ecobuild sync continue は
    衝突を直したファイルを自分で登録します。
    """

    def action(inv):
        module = inv.module
        relative = tuple(module.relative_path(p, inv.cwd) for p in paths)
        return module.require_task_branch("ステージ").stage(*relative, all=all)

    def render(r):
        listed = f"指定した {len(paths)} 件をステージしました" if paths and not all else "すべての変更をステージしました"
        return f"{listed}（ステージ済みの合計：{len(r.staged)} ファイル）"

    return run_command("task add", action, render, json_output=json)
