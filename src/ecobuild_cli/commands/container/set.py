from typing import Annotated

from ecobuild_bundle import container as _container
from ..._output import run_command, split_semicolons
from ._render import render


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
        return _container.configure(inv.module.root, image="" if default_image else (image or None),
                                    deny=() if no_deny else (split_semicolons(deny) or None))

    return run_command("container set", action, lambda r: render(r, "設定を変えました" if r.changed else "設定は同じです"),
                       json_output=json)
