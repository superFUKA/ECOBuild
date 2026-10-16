from typing import Annotated

from ecobuild_cli.kit import render_profiles as render, run_command


def command(
    name: Annotated[str, "ビルド設定の名前"],
    project: Annotated[str, "上書きするProject"],
    type: Annotated[str, "ライブラリの形式（static／shared／interface。このProjectを使う側のリンクもこの形式になる）"] = "",
    cpp_standard: Annotated[int, "このProjectのC++の規格（17／20／23）"] = 0,
    artifact_directory: Annotated[str, "成果物の置き場所（ビルドツリーからの相対）"] = "",
    test_parallel: Annotated[int, "このテスト用Projectを並列に実行する数"] = 0,
    googletest_archive: Annotated[str, "このテスト用Projectが使う GoogleTest のZIP"] = "",
    clear: Annotated[bool, "このProjectの上書きをすべて外す"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ビルド設定の、Projectごとの上書きを設定します（指定した項目で置き換え）。

    ecobuild.toml が変わるので、作業空間でコミットしてください。

    構成・生成器・アーキテクチャはモジュール全体で1つです（依存でつながるProjectは揃っている必要があります）。
    """

    def action(inv):
        values = {key: value for key, value in (
            ("type", type), ("cpp_standard", cpp_standard), ("artifact_directory", artifact_directory),
            ("test_parallel", test_parallel), ("googletest_archive", googletest_archive)) if value}
        return inv.module.set_profile_project(name, project, None if clear else values)

    return run_command("profile project", action, render, json_output=json)
