from typing import Annotated

from ....errors import EcoBuildError, ErrorCode
from ..._output import optional_argument, run_command, split_list
from ._common import render_details, target_project


def command(
    *projects: Annotated[str, "対象のProject（--project と同じ）"],
    project: Annotated[str, "対象のProject（既定：今いるProject、テスト用を除いてProjectが1つならそれ）"] = "",
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
    folder: Annotated[str, "Visual Studio のソリューションフォルダー（/ 区切り。例：Libraries/Math）"] = "",
    clear_folder: Annotated[bool, "ソリューションフォルダーを既定（モジュールの設定）に戻す"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Projectの設定を変えます。管理ファイルが変わるので、作業空間でコミットしてください。

    ビルドのたびに選ぶもの（C++の規格・ライブラリの形式の切り替え等）は ecobuild profile で設定します。
    """
    project = optional_argument(projects, project, "--project", json)

    def action(inv):
        if export_all not in ("", "on", "off"):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--export-all は on か off です。")
        return inv.module.set_project(
            target_project(inv, project), types=split_list(type),
            add_defines=split_list(add_define), remove_defines=split_list(remove_define),
            add_public_defines=split_list(add_public_define), remove_public_defines=split_list(remove_public_define),
            add_include_directories=split_list(add_include), remove_include_directories=split_list(remove_include),
            add_source_directories=split_list(add_source_dir), remove_source_directories=split_list(remove_source_dir),
            export_all_symbols=None if not export_all else export_all == "on",
            folder=folder or None, clear_folder=clear_folder)

    return run_command("project set", action, render_details, json_output=json)
