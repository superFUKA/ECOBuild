from typing import Annotated

from ecobuild.config import Profile
from ecobuild_cli.kit import render_profiles as render, run_command


def command(
    name: Annotated[str, "ビルド設定の名前"],
    configuration: Annotated[str, "構成（Debug＝編集可能でインストール・Release＝さらに配布用のパッケージを作る）"] = "Debug",
    parallel: Annotated[int, "並列の数"] = 1,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ビルド設定を追加（同じ名前なら上書き）します。ecobuild.toml が変わるので、タスクブランチでコミットしてください。"""
    return run_command("profile add", lambda inv: inv.module.add_profile(name, Profile(configuration, False, parallel)),
                       render, json_output=json)
