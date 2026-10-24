from typing import Annotated

from ecobuild.errors import EcoBuildError
from ecobuild_cpp.errors import ErrorCode
from ecobuild_cli.kit import optional_argument, run_command, split_list, split_semicolons
from ._common import render_details, target_project


def command(
    *projects: Annotated[str, "対象のProject（--project と同じ）"],
    project: Annotated[str, "対象のProject（既定：今いるProject、テスト用を除いてProjectが1つならそれ）"] = "",
    kind: Annotated[str, "種類を変える：app（実行ファイル）／library（静的ライブラリ）／shared（共有ライブラリ）。ソース・設定・リンクは保つ"] = "",
    no_test: Annotated[bool, "--kind library・shared で、組のテスト用Project（<名前>Test）を作らない"] = False,
    type: Annotated[str, "定義・インクルードを変える形式（ライブラリ：static・shared・interface のカンマ区切り。既定はすべて）"] = "",
    add_define: Annotated[str, "このProjectだけの定義を足す（カンマ区切り。例：USE_FOO,LEVEL=2）"] = "",
    remove_define: Annotated[str, "このProjectだけの定義を外す（カンマ区切り）"] = "",
    add_public_define: Annotated[str, "使う側にも伝わる定義を足す（カンマ区切り）"] = "",
    remove_public_define: Annotated[str, "使う側にも伝わる定義を外す（カンマ区切り）"] = "",
    add_include: Annotated[str, "インクルードディレクトリを足す（Projectからの相対、カンマ区切り）"] = "",
    remove_include: Annotated[str, "インクルードディレクトリを外す（カンマ区切り）"] = "",
    add_source_dir: Annotated[str, "ソースディレクトリを足す（Projectからの相対、カンマ区切り。中のファイルがビルドに入る）"] = "",
    remove_source_dir: Annotated[str, "ソースディレクトリを外す（カンマ区切り）"] = "",
    export_all: Annotated[str, "Windowsで共有ライブラリのすべての関数を書き出す（on／off。ライブラリだけ）"] = "",
    entry_point: Annotated[str, "実行ファイルの入口の関数（main・wmain・WinMain・wWinMain。それ以外は MSVC の /ENTRY）"] = "",
    gui: Annotated[str, "GUIアプリにする（on／off。既定は入口の関数で決まる：WinMain・wWinMain ならGUI）"] = "",
    add_system_lib: Annotated[str, "OSのライブラリを名前でリンクする（カンマ区切り。例：ws2_32,d3d11）"] = "",
    remove_system_lib: Annotated[str, "OSのライブラリを外す（カンマ区切り）"] = "",
    add_compile_option: Annotated[str, "コンパイルオプションを足す（セミコロン区切り。例：/permissive-;/Zc:__cplusplus）"] = "",
    remove_compile_option: Annotated[str, "コンパイルオプションを外す（足したときと同じ条件で）"] = "",
    add_link_option: Annotated[str, "リンクオプションを足す（セミコロン区切り。例：/STACK:8388608）"] = "",
    remove_link_option: Annotated[str, "リンクオプションを外す（足したときと同じ条件で）"] = "",
    add_conditional_define: Annotated[str, "条件付きの定義を足す（セミコロン区切り。NAME か NAME=値。例：_CRT_SECURE_NO_WARNINGS）"] = "",
    remove_conditional_define: Annotated[str, "条件付きの定義を外す（足したときと同じ条件で）"] = "",
    compiler: Annotated[str, "上のオプション・定義を足す・外すときの条件：コンパイラの種類（MSVC・GNU・Clang 等。既定はすべて）"] = "",
    configuration: Annotated[str, "上のオプション・定義を足す・外すときの条件：構成（Debug・Release 等。既定はすべて）"] = "",
    warning_level: Annotated[str, "警告のレベル（0〜4。MSVC の /W0〜/W4。default で既定〔MSVCは /W3〕に戻す）"] = "",
    warnings_as_errors: Annotated[str, "警告をエラーにする（on／off）"] = "",
    event: Annotated[str, "ビルドイベントの段階（pre_build＝コンパイルの前・pre_link＝リンクの前・post_build＝ビルドの後）"] = "",
    add_build_event: Annotated[str, "--event の段階で実行するコマンドを足す（セミコロン区切り。1つは引数を空白で区切った1行。例：python tools/gen.py）"] = "",
    remove_build_event: Annotated[str, "--event の段階のコマンドを外す"] = "",
    add_output_file: Annotated[str, "ビルドのたびに、できたファイルの横へ（Projectでの場所のまま）コピーするファイル・フォルダー（Projectからの相対、カンマ区切り）"] = "",
    remove_output_file: Annotated[str, "コピーするファイル・フォルダーを外す（カンマ区切り）"] = "",
    folder: Annotated[str, "Visual Studio のソリューションフォルダー（/ 区切り。例：Libraries/Math）"] = "",
    clear_folder: Annotated[bool, "ソリューションフォルダーを既定（モジュールの設定）に戻す"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Projectの設定を変えます。管理ファイルが変わるので、タスクブランチでコミットしてください。

    ビルドのたびに選ぶもの（C++の規格・ライブラリの形式の切り替え等）は ecobuild profile で設定します。

    --kind で種類を変えます（作り直しても、ソース・設定・リンク・main は保ちます。ほかの設定はその後で変えます）。
    ライブラリにすると、入口の関数・GUIアプリの設定を外し、project add と同じく、ないファイル（include/<名前>/<名前>.h・
    src/<名前>.cpp）と、実行ファイルからなら組のテスト用Project <名前>Test を作ります（あるものは上書きしません）。実行ファイルにすると、入口は main
    になり、src/main.cpp がなければ置きます。ほかのProjectがリンクしているライブラリ・main は、実行ファイルにできません。
    """
    project = optional_argument(projects, project, "--project", json)

    def action(inv):
        for option, value in (("--export-all", export_all), ("--gui", gui), ("--warnings-as-errors", warnings_as_errors)):
            if value not in ("", "on", "off"):
                raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{option} は on か off です。")
        if warning_level not in ("", "default", *map(str, range(5))):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--warning-level は 0〜4 か default です。")
        if no_test and kind not in ("library", "shared"):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--no-test は --kind library・shared と使います。")
        return inv.module.set_project(
            target_project(inv, project), kind=kind or None, test=not no_test, types=split_list(type),
            add_defines=split_list(add_define), remove_defines=split_list(remove_define),
            add_public_defines=split_list(add_public_define), remove_public_defines=split_list(remove_public_define),
            add_include_directories=split_list(add_include), remove_include_directories=split_list(remove_include),
            add_source_directories=split_list(add_source_dir), remove_source_directories=split_list(remove_source_dir),
            export_all_symbols=None if not export_all else export_all == "on",
            folder=folder or None, clear_folder=clear_folder,
            entry_point=entry_point or None, gui=None if not gui else gui == "on",
            add_system_libraries=split_list(add_system_lib), remove_system_libraries=split_list(remove_system_lib),
            add_compile_options=split_semicolons(add_compile_option),
            remove_compile_options=split_semicolons(remove_compile_option),
            add_link_options=split_semicolons(add_link_option), remove_link_options=split_semicolons(remove_link_option),
            add_conditional_defines=split_semicolons(add_conditional_define),
            remove_conditional_defines=split_semicolons(remove_conditional_define),
            compiler=compiler or None, configuration=configuration or None,
            warning_level=int(warning_level) if warning_level.isdigit() else None,
            default_warning_level=warning_level == "default",
            warnings_as_errors=None if not warnings_as_errors else warnings_as_errors == "on",
            event=event or None, add_build_events=split_semicolons(add_build_event),
            remove_build_events=split_semicolons(remove_build_event),
            add_output_files=split_list(add_output_file), remove_output_files=split_list(remove_output_file))

    return run_command("project set", action, render_details, json_output=json)
