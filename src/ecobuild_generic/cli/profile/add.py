from typing import Annotated

from ecobuild.config import Profile
from ecobuild_cli.kit import render_profiles as render, run_command


def command(
    name: Annotated[str, "ビルド設定の名前"],
    configuration: Annotated[str, "構成（[commands] のコマンドの {configuration} に入る）"] = "Debug",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ビルド設定を追加（同じ名前なら上書き）します。ecobuild.toml が変わるので、作業空間でコミットしてください。"""
    return run_command("profile add", lambda inv: inv.module.add_profile(name, Profile(configuration)),
                       render, json_output=json)
