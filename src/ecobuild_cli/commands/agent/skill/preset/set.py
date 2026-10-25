from typing import Annotated

from ecobuild_agent import skills as _skills
from ecobuild_agent.results import skill_view

from ....._output import run_command
from .. import _render
from ..set import changes


def command(name: Annotated[str, "このPCのスキルの名前"],
            description: Annotated[str, "説明（何をするか・いつ使うか）"] = "",
            document: Annotated[str, "本文のファイル（- なら標準入力）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """このPCのスキルの説明・本文を変えます（書いたオプションだけを変えます）。"""
    def action(inv):
        new_description, text = changes(description, document)
        return skill_view(_skills.update_preset(name, description=new_description, document=text), document=True)

    return run_command("agent skill preset set", action, lambda r: "変えました：\n" + _render.details(r),
                       json_output=json)
