from typing import Annotated

from ..._output import lines, run_command


def command(
    dry_run: Annotated[bool, "片付ける対象を表示するだけにする"] = False,
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Issueが閉じた作業空間を片付けます（GitHubにないコミットがある作業空間は残します）。"""

    def action(inv):
        module = inv.module
        preview = module.clean_workspaces(dry_run=True)
        if dry_run or not preview.removed:
            return preview
        inv.confirm(f"作業空間 {', '.join(preview.removed)} を片付けますか？")
        return module.clean_workspaces()

    def render(r):
        return lines(
            ("片付ける対象：" if r.dry_run else "片付けました：") + (", ".join(r.removed) or "なし"),
            "\n".join(f"残しました：{s.branch}（{s.reason}）" for s in r.skipped) or None,
            f"{r.switched_to} に移りました" if r.switched_to else None,
        )

    return run_command("task clean", action, render, json_output=json, yes=yes)
