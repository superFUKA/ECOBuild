from typing import Annotated

from ....errors import EcoBuildError, ErrorCode
from ..._output import optional_argument, run_command, split_list
from ._common import pairs, render_details, target_project


def command(
    *library: Annotated[str, "リンクする、同じモジュールのライブラリのProject"],
    project: Annotated[str, "リンクする側のProject（既定：今いるProject、テスト用を除いてProjectが1つならそれ）"] = "",
    type: Annotated[str, "リンクの形式（static・shared・interface。既定は相手の作成時の形式、--file では static）"] = "",
    package: Annotated[str, "CMakeのパッケージ名（find_package の名前。--target・--directory と一緒に）"] = "",
    cmake: Annotated[str, "CMakeのソースのディレクトリ（add_subdirectory する。Projectからの相対。--target と一緒に）"] = "",
    target: Annotated[str, "--package・--cmake でリンクするCMakeのターゲット（例：fmt::fmt）"] = "",
    directory: Annotated[str, "--package の <名前>Config.cmake があるディレクトリ（Projectからの相対）"] = "",
    file: Annotated[str, "ビルド済みのライブラリ（構成=パス のカンマ区切り。Projectからの相対）"] = "",
    implib: Annotated[str, "--file の共有ライブラリのインポートライブラリ（構成=パス のカンマ区切り）"] = "",
    include: Annotated[str, "--file のインクルードディレクトリ（Projectからの相対、カンマ区切り）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Projectにライブラリをリンクします。

    リンクできるのは、同じモジュールのライブラリ（LIBRARY）・CMakeのパッケージ（--package）・CMakeのソース（--cmake）・
    ビルド済みのファイル（--file）です。他のモジュール（GitHubのリポジトリ）は ecobuild link でリンクします。管理ファイルが変わるので、作業空間でコミットしてください。
    """
    library = optional_argument(library, "", "LIBRARY", json)

    def action(inv):
        module = inv.module
        name = target_project(inv, project)
        modes = [m for m, on in (("LIBRARY", library), ("--package", package), ("--cmake", cmake),
                                 ("--file", file or implib or include)) if on]
        if len(modes) != 1:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                                "リンクするものを1つ指定してください（LIBRARY・--package・--cmake・--file のどれか）。")
        if package or cmake:
            if not target or (package and not directory):
                raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                                    "--package には --target と --directory、--cmake には --target が要ります。")
            if type:
                raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--type は --package・--cmake では使えません（形式はCMakeが決めます）。")
            return (module.link_package(name, package, target=target, directory=directory) if package
                    else module.link_cmake(name, cmake, target=target))
        if library:
            return module.link_project(name, library, as_type=type or None)
        return module.link_library_file(name, kind=type or "static", locations=pairs(file, "--file"),
                                        import_libraries=pairs(implib, "--implib"),
                                        include_directories=split_list(include))

    return run_command("project link", action, render_details, json_output=json)
