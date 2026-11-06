from typing import Annotated

import ecobuild_container as _container
from ecobuild_agent import inside as _agent
from ..._output import run_command, split_semicolons, usage_error
from ._render import render, view


def command(image: Annotated[str, "使うイメージ（既定は型のイメージ）"] = "",
            default_image: Annotated[bool, "使うイメージを型のイメージに戻す"] = False,
            deny: Annotated[str, "エージェントに使わせないもの（Claude Code の許可の規則を ; で区切る。例 Bash(git push --force:*);WebFetch）"] = "",
            no_deny: Annotated[bool, "使わせないものの設定を消す（このPCの agent_deny だけになる）"] = False,
            host_run: Annotated[str, "on：エージェントに、ビルド・テスト等をこのPCで実行させる（ツール host_run。エージェントの書いたコードがコンテナの外で動く）。off：させない（既定）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """この作業空間のコンテナだけの設定を変えます（このPCの ecobuild.local.toml。コミットしません）。

    使わせないものは、このPCの設定（ecobuild config set agent_deny）に足されます。イメージを変えると、次に動かすときに
    コンテナを作り直します（作業空間のファイルはそのまま）。
    --host-run on：中のエージェントに、ビルド・テスト・実行・確認をこのPC（Windows 等）で行うツール host_run を渡します
    （ecobuild host <コマンド> と同じ。エージェントの書いたコードが、コンテナの守りなしにこのPCで動きます）。
    許したことはこのPCだけに残し（ECOBUILD_HOME。コンテナからは見えない）、起動し直したエージェントから効きます。
    """
    if host_run not in ("", "on", "off"):
        return usage_error(f"--host-run は on か off です：{host_run}", json)

    def action(inv):
        rules = () if no_deny else (split_semicolons(deny) or None)
        denied = rules is not None and _agent.set_deny(inv.module.root, rules)   # 使わせないものはエージェントの拡張が持つ
        hosted = bool(host_run) and _agent.set_host_run(inv.module.root, host_run == "on")
        result = _container.configure(inv.module.root, image="" if default_image else (image or None))
        return view(result, changed=result.changed or denied or hosted)

    return run_command("container set", action, lambda r: render(r, "設定を変えました" if r.changed else "設定は同じです"),
                       json_output=json)
