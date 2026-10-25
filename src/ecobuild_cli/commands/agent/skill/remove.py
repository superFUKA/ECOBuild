from typing import Annotated

from ecobuild_agent import skills as _skills
from ecobuild_agent.results import skill_view

from ...._output import run_command
from .. import _change


def command(name: Annotated[str, "スキルの名前"],
            yes: Annotated[bool, "確認せずに実行する"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュールのスキルをフォルダーごと消し、タスクブランチでコミットします。"""
    def action(inv):
        _skills.load(name, inv.module.root)          # ないものは確認の前に知らせる
        inv.confirm(f"スキル「{name}」をフォルダーごと消しますか？")
        removed, sha = _change.in_task_branch(inv, f"スキル「{name}」を消す",
                                              lambda module: _skills.remove(module.root, name))
        return skill_view(removed, document=True, committed=sha)

    return run_command("agent skill remove", action, lambda r: f"スキル「{r.name}」を消しました",
                       json_output=json, yes=yes)
