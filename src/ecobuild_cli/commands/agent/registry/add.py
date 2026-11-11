import sys
from dataclasses import replace
from typing import Annotated

import click
from click.core import ParameterSource
from ecobuild_agent import registry as _registry
from ecobuild_agent import rules as _rules
from ecobuild_agent.results import registration_view

from ...._output import run_command
from .. import _change
from . import _render


def command(name: Annotated[str, "登録の名前（英小文字・数字・-・_）"],
            from_preset: Annotated[str, "写すプリセットの名前（見本の lead・manager・worker と、このPCのプリセット。agent preset list）"] = "",
            from_dir: Annotated[str, "取り込むフォルダー（agent.toml と agent.md がある）"] = "",
            title: Annotated[str, "表示名（書かなければ、写した元のまま。空の登録なら名前）"] = "",
            human_start: Annotated[bool, "人が起動できる（--no-human-start で起動できない。書かなければ、写した元のまま）"] = False,
            no_owner_tools: Annotated[bool, "ブランチを変える（コミット・push・提出）ツールを渡さない（変えたファイルは人が見て、人がコミット・提出する。この登録より強くなる子は、起動してよい子から外す）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュールにエージェントの登録を足し、タスクブランチでコミットします。

    置き場所は .ecobuild/agents/registry/<名前>/ です。
    --from-preset でプリセット（見本も）を写すか、--from-dir でフォルダーを取り込みます。どちらもなければ、同じ名前の
    プリセットを写し、それもなければ空の登録を作ります。中身は ecobuild agent registry set で変えます
    （表示名・人が起動できるか・コミットや提出をさせないかは、足すときにも決められます）。

    例：
      ecobuild agent registry add reviewer --from-preset worker
      ecobuild agent registry add reviewer --from-preset worker --title レビュー役 --human-start --no-owner-tools
    """
    def action(inv):
        context = click.get_current_context()
        fields = {}
        if title.strip():
            fields["title"] = title.strip()
        if context.get_parameter_source("human_start") not in (ParameterSource.DEFAULT, ParameterSource.DEFAULT_MAP):
            fields["human_start"] = human_start

        def change(module):
            added = _registry.add(module.root, name, from_preset=from_preset or None, from_dir=from_dir or None)
            if no_owner_tools:
                fields["tools"] = _rules.tools_without_owner(
                    added.tools, _rules.tool_list(module.root, (sys.executable, "-m", "ecobuild_cli")))
                narrowed = replace(added, tools=fields["tools"])    # 狭めた登録より強くなる子は、持てない
                known = {r.name: r for r in _registry.list_registrations(module.root)}
                fields["children"] = tuple(child for child in added.children
                                           if child not in known or not _registry.stronger(known[child], narrowed))
                dropped = [child for child in added.children if child not in fields["children"]]
                if dropped:     # 黙って外さない
                    inv.notices.append(f"起動してよい子から {'・'.join(dropped)} を外しました（コミット・push・提出のツールを持つので、"
                                       f"この登録より強くなります）。子として使うなら、その登録のツールも狭めてから "
                                       f"ecobuild agent registry set {name} --children で足してください。")
            if not fields:
                return added
            try:
                return _registry.update(module.root, name, **fields)
            except Exception:       # 決めた値で保存できなければ、足したものを残さない
                _registry.remove(module.root, name)
                raise

        added, sha = _change.in_task_branch(inv, f"エージェントの登録「{name}」を足す", change)
        return registration_view(added, document=True, pending=True, committed=sha)

    return run_command("agent registry add", action, lambda r: "登録しました：" + _render.details(r), json_output=json)
