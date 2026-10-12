from typing import Annotated

from ....config import Profile
from ..._output import run_command
from .list import render


def command(
    name: Annotated[str, "ビルド設定の名前"],
    configuration: Annotated[str, "構成（Debug／Release／RelWithDebInfo／MinSizeRel）"] = "Debug",
    shared: Annotated[bool, "ライブラリ（依存先を含む）を共有ライブラリにする"] = False,
    parallel: Annotated[int, "並列ビルドの数"] = 1,
    architecture: Annotated[str, "C++：アーキテクチャ（x64／Win32／ARM64。既定はホスト・コンパイラの既定）"] = "",
    cpp_standard: Annotated[int, "C++：C++の規格（17／20／23。既定は20）"] = 0,
    generator: Annotated[str, "C++：CMakeの生成器（Visual Studio 17 2022／Visual Studio 18 2026／Ninja Multi-Config。既定はOSごと）"] = "",
    toolset: Annotated[str, "C++：ツールセット（Visual Studio は v143 等、Ninja＋MSVC は 14.44 等）"] = "",
    c_compiler: Annotated[str, "C++：Cコンパイラ（Ninjaだけ。名前か絶対パス）"] = "",
    cxx_compiler: Annotated[str, "C++：C++コンパイラ（Ninjaだけ。名前か絶対パス。例：clang++）"] = "",
    toolchain_file: Annotated[str, "C++：CMakeのツールチェーンファイル（絶対パス）"] = "",
    test_parallel: Annotated[int, "C++：テストを並列に実行する数（既定は1）"] = 0,
    stop_on_test_failure: Annotated[bool, "C++：テスト用のProjectが失敗したら、残りのテストを実行しない"] = False,
    googletest_archive: Annotated[str, "C++：GoogleTestのZIP（オフラインで使う。既定はダウンロード）"] = "",
    no_fetch: Annotated[bool, "C++：足りない依存先を、ビルドの前に自動でcloneしない"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ビルド設定を追加（同じ名前なら上書き）します。ecobuild.toml が変わるので、作業空間でコミットしてください。

    Projectごとの上書き（ecobuild profile project）は、上書きしても残ります。
    """

    def action(inv):
        module = inv.module
        options = {key: value for key, value in (
            ("architecture", architecture), ("cpp_standard", cpp_standard), ("generator", generator),
            ("toolset", toolset), ("c_compiler", c_compiler), ("cxx_compiler", cxx_compiler),
            ("toolchain_file", toolchain_file), ("test_parallel", test_parallel),
            ("googletest_archive", googletest_archive)) if value}
        if stop_on_test_failure:
            options["test_continue_on_failure"] = False
        if no_fetch:
            options["fetch_git"] = False
        existing = module.config.profiles.get(name)
        return module.add_profile(name, Profile(configuration, shared, parallel, options,
                                                dict(existing.projects) if existing else {}))

    return run_command("profile add", action, render, json_output=json)
