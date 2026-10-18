from typing import Annotated

from ecobuild_bundle import container as _container
from ..._module import PROGRAM
from ..._output import lines, run_command, usage_error


def command(
    on: Annotated[bool, "この作業空間をコンテナにする"] = False,
    off: Annotated[bool, "この作業空間をコンテナにしない（このPCで動かす）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """今いる作業空間をコンテナにするかを選びます（--on・--off。どちらもなければ、今の選択を表示します）。

    選択はこのPCの、この作業空間だけのものです（ecobuild.local.toml、コミットしません）。ファイルは今の場所に置いた
    まま、コンテナにはこの作業空間のフォルダだけを見せます。コンテナを使うには Docker が要ります
    （ecobuild setup --docker）。今は選ぶだけで、ビルド・テスト・エージェントはまだこのPCで動きます。
    """
    if on and off:
        return usage_error("--on と --off は一緒に指定できません", json)

    def action(inv):
        root = inv.module.root
        return _container.show(root) if not (on or off) else _container.choose(root, on)

    def render(r):
        state = "コンテナにします" if r.container else "コンテナにしません（このPCで動かします）"
        return lines(
            f"{r.path}：{state}" + ("" if r.changed or not (on or off) else "（前からこの選択です）"),
            (f"Docker：使えます（{r.docker_detail}）" if r.docker_ready else
             f"Docker：まだ使えません（{r.docker_detail}）。{PROGRAM} setup --docker で導入できます") if r.container else None,
            "今は選ぶだけです。ビルド・テスト・エージェントはまだこのPCで動きます" if r.container else None,
        )

    return run_command("workspace container", action, render, json_output=json)
