from typing import Annotated

import ecobuild_container as _container
from ecobuild_agent import inside as _agent
from ..._output import run_command, split_semicolons
from ._render import render, view


def command(image: Annotated[str, "使うイメージ（既定は型のイメージ）"] = "",
            default_image: Annotated[bool, "使うイメージを型のイメージに戻す"] = False,
            deny: Annotated[str, "エージェントに使わせないもの（Claude Code の許可の規則を ; で区切る。例 Bash(git push --force:*);WebFetch）"] = "",
            no_deny: Annotated[bool, "使わせないものの設定を消す（このPCの agent_deny だけになる）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """この作業空間のコンテナだけの設定を変えます（このPCの ecobuild.local.toml。コミットしません）。

    使わせないものは、このPCの設定（ecobuild config set agent_deny）に足されます。イメージを変えると、次に動かすときに
    コンテナを作り直します（作業空間のファイルはそのまま）。
    """
    def action(inv):
        rules = () if no_deny else (split_semicolons(deny) or None)
        denied = rules is not None and _agent.set_deny(inv.module.root, rules)   # 使わせないものはエージェントの拡張が持つ
        result = _container.configure(inv.module.root, image="" if default_image else (image or None))
        return view(result, changed=result.changed or denied)

    return run_command("container set", action, lambda r: render(r, "設定を変えました" if r.changed else "設定は同じです"),
                       json_output=json)
