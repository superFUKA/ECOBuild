import sys
from typing import Annotated

import click
from click.core import ParameterSource
from ecobuild_agent import rules as _rules
from ecobuild_agent.results import AgentToolFit

from ...._output import lines, run_command, split_list


def command(name: Annotated[str, "登録の名前"],
            tools: Annotated[str, "確かめる、渡すツールの名前の並び（カンマ区切り。* 等の fnmatch。書かなければ今の並び）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """登録に渡すツールをこう選ぶとどうなるかを確かめます（保存する前に。何も変えません）。

    渡るツールの数（ブランチを変える〔コミット・push・提出〕ツールの数）、多すぎないか、この登録より強くなる登録
    （許すツールが多い登録。子にできません）、この登録を子に持つのに弱くなる登録（あると保存できません）を出します。

    例：
      ecobuild agent registry fit worker --tools "status,diff,task_*"
    """
    def action(inv):
        source = click.get_current_context().get_parameter_source("tools")
        asked = None if source in (ParameterSource.DEFAULT, ParameterSource.DEFAULT_MAP) else split_list(tools)
        root = inv.module.root
        return AgentToolFit(**_rules.tool_fit(root, name, asked, _rules.tool_list(root, (sys.executable, "-m", "ecobuild_cli"))))

    return run_command("agent registry fit", action, render, json_output=json)


def render(r) -> str:
    return lines(
        f"{r.name}：{r.count} / {r.total} 個のツールを渡します"
        + (f"（コミット・提出のツール {r.owner} 個を含む）" if r.owner else "（コミット・提出はさせない）"),
        *([f"  多めです：ツールが {r.limit} を超えると選び方が落ちやすい（仕事に要るものに絞るか、手順はスキル・文書に）"]
          if r.too_many else []),
        *([f"  この登録より強い（子にできない）：{'・'.join(r.stronger)}"] if r.stronger else []),
        *([f"  この登録を子に持つのに弱くなる（保存できない）：{'・'.join(r.parents)}"] if r.parents else []),
    )
