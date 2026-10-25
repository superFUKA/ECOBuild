from typing import Annotated

from ecobuild_agent import skills as _skills
from ecobuild_agent.results import skill_view

from ....._output import run_command


def command(name: Annotated[str, "このPCのスキルの名前"],
            yes: Annotated[bool, "確認せずに実行する"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """このPCのスキルをフォルダーごと消します。"""
    def action(inv):
        _skills.load_preset(name)
        inv.confirm(f"このPCのスキル「{name}」をフォルダーごと消しますか？")
        return skill_view(_skills.remove_preset(name), document=True)

    return run_command("agent skill preset remove", action, lambda r: f"このPCのスキル「{r.name}」を消しました",
                       json_output=json, yes=yes)
