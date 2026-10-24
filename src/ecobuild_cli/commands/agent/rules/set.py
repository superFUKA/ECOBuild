from typing import Annotated

import click
from click.core import ParameterSource
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_agent import rules as _rules

from ...._output import run_command, split_list
from . import _render


def command(common: Annotated[str, "全エージェント共通の文（空なら消す）"] = "",
            role: Annotated[str, "--text・--deny を当てる登録の名前（worker 等）"] = "",
            text: Annotated[str, "その登録のエージェントだけへの文（空なら消す）"] = "",
            deny: Annotated[str, "その登録に使わせないツール（カンマ区切り。task_submit・children_* 等の fnmatch。空なら絞らない）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュールのエージェント向けの決まりを変えて、タスクブランチでコミットします（書いたオプションだけを変えます）。

    .ecobuild/agents/ に書きます。起動したエージェントに効くのは、提出して作成元のブランチに取り込まれてからです。
    使わせないツールは、登録（このPC）で許したものを絞るだけです。

    例：
      ecobuild agent rules set --common "前後がつながった段階（調べる→設計→実装）は分けず、自分で進める"
      ecobuild agent rules set --role worker --deny "children_*"
    """
    context = click.get_current_context()

    def given(option):
        return context.get_parameter_source(option) not in (ParameterSource.DEFAULT, ParameterSource.DEFAULT_MAP)

    def action(inv):
        if not any(given(key) for key in ("common", "text", "deny")):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "変える項目がありません。",
                                hint="--common、または --role と --text・--deny を書いてください。")
        module = inv.module
        if module.repository.current_task_branch() is None:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "モジュールの決まりは、タスクブランチで変えます（コミットして PR で取り込みます）。",
                                hint="ecobuild task start でタスクブランチを作ってから、もう一度実行してください。")
        before = module.own_changes()
        changed = _rules.write(module.root, common=common if given("common") else None, role=role.strip(),
                               text=text if given("text") else None, deny=split_list(deny) if given("deny") else None)
        result = module.commit_own_changes("エージェントの決まりを変える", before) if changed else None
        return _rules.view(module.root, changed=tuple(changed), committed=result.sha if result else "")

    return run_command("agent rules set", action, _render.details, json_output=json)
