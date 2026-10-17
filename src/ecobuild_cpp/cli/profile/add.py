from typing import Annotated

from ecobuild.config import Profile
from ecobuild_cli.kit import render_profiles as render, run_command


def command(
    name: Annotated[str, "ビルド設定の名前"],
    configuration: Annotated[str, "構成（Debug／Release／RelWithDebInfo／MinSizeRel）"] = "Debug",
    shared: Annotated[bool, "ライブラリ（依存先を含む）を共有ライブラリにする"] = False,
    parallel: Annotated[int, "並列ビルドの数"] = 1,
    architecture: Annotated[str, "アーキテクチャ（x64／Win32／ARM64。既定はホスト・コンパイラの既定）"] = "",
    cpp_standard: Annotated[int, "C++の規格（17／20／23。既定は20）"] = 0,
    generator: Annotated[str, "CMakeの生成器（Visual Studio 17 2022／Visual Studio 18 2026／Ninja Multi-Config。既定はOSごと）"] = "",
    toolset: Annotated[str, "ツールセット（Visual Studio は v143 等、Ninja＋MSVC は 14.44 等）"] = "",
    c_compiler: Annotated[str, "Cコンパイラ（Ninjaだけ。名前か絶対パス）"] = "",
    cxx_compiler: Annotated[str, "C++コンパイラ（Ninjaだけ。名前か絶対パス。例：clang++）"] = "",
    toolchain_file: Annotated[str, "CMakeのツールチェーンファイル（絶対パス）"] = "",
    windows_sdk: Annotated[str, "Windows SDKの版（MSVCだけ。例：10.0.22621.0。既定はCMakeの選択）"] = "",
    test_parallel: Annotated[int, "テストを並列に実行する数（既定は1）"] = 0,
    stop_on_test_failure: Annotated[bool, "テスト用のProjectが失敗したら、残りのテストを実行しない"] = False,
    googletest_archive: Annotated[str, "GoogleTestのZIP（オフラインで使う。既定はダウンロード）"] = "",
    no_fetch: Annotated[bool, "足りない依存先を、ビルドの前に自動でcloneしない"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ビルド設定を追加（同じ名前なら上書き）します。ecobuild.toml が変わるので、タスクブランチでコミットしてください。

    Projectごとの上書き（ecobuild profile project）は、上書きしても残ります。
    """

    def action(inv):
        module = inv.module
        options = {key: value for key, value in (
            ("architecture", architecture), ("cpp_standard", cpp_standard), ("generator", generator),
            ("toolset", toolset), ("c_compiler", c_compiler), ("cxx_compiler", cxx_compiler),
            ("toolchain_file", toolchain_file), ("windows_sdk", windows_sdk), ("test_parallel", test_parallel),
            ("googletest_archive", googletest_archive)) if value}
        if stop_on_test_failure:
            options["test_continue_on_failure"] = False
        if no_fetch:
            options["fetch_git"] = False
        existing = module.config.profiles.get(name)
        return module.add_profile(name, Profile(configuration, shared, parallel, options,
                                                dict(existing.projects) if existing else {}))

    return run_command("profile add", action, render, json_output=json)
