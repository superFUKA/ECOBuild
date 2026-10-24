from typing import Annotated

from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command
from ..registry import _render
from ..registry.set import changes


def command(name: Annotated[str, "プリセットの名前"],
            title: Annotated[str, "表示名"] = "",
            human_start: Annotated[bool, "人が起動できる（--no-human-start で起動できない）"] = False,
            model: Annotated[str, "モデル（空なら Claude Code の既定）"] = "",
            tools: Annotated[str, "渡すツールの名前の並び（カンマ区切り。* 等の fnmatch。空なら何も渡さない）"] = "",
            children: Annotated[str, "起動してよい子の登録の名前（カンマ区切り。空なら子を起動しない）"] = "",
            max_children: Annotated[int, "同時に持てる子の数の上限"] = 0,
            first_prompt: Annotated[str, "起動のときの最初の発言"] = "",
            document: Annotated[str, "文書（agent.md）を読むファイル（- なら標準入力）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """プリセットの設定・文書を変えます（書いたオプションだけ）。

    見本の名前なら、このPCのプリセットとして写してから変えます（見本そのものは変わりません。元に戻すには
    ecobuild agent preset remove）。
    """
    def action(inv):
        fields, text = changes(title=title, human_start=human_start, model=model, tools=tools, children=children,
                               max_children=max_children, first_prompt=first_prompt, document=document)
        return registration_view(_registry.update_preset(name, document=text, **fields), document=True)

    return run_command("agent preset set", action, lambda r: "変えました：\n" + _render.details(r), json_output=json)
