from typing import Annotated

from ....config import Profile
from ..._output import run_command
from .list import render


def command(
    name: Annotated[str, "ビルド設定の名前"],
    configuration: Annotated[str, "構成（Debug／Release／RelWithDebInfo／MinSizeRel）"] = "Debug",
    shared: Annotated[bool, "ライブラリ（依存先を含む）を共有ライブラリにする"] = False,
    parallel: Annotated[int, "並列ビルドの数"] = 1,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ビルド設定を追加（同じ名前なら上書き）します。ecobuild.toml が変わるので、作業空間でコミットしてください。"""
    return run_command("profile add",
                       lambda inv: inv.module.add_profile(name, Profile(configuration, shared, parallel)),
                       render, json_output=json)
