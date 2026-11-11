from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_cli.kit import run_command

from . import render


def command(
    main: Annotated[str, "他のモジュールからリンクされるProject（main）を変える（ライブラリであること）"] = "",
    no_main: Annotated[bool, "main をなしにする（他のモジュールからリンクできなくなる）"] = False,
    projects_folder: Annotated[str, "Visual Studio で自分のProjectを入れるソリューションフォルダー（既定 Projects）"] = "",
    linked_folder: Annotated[str, "リンク先のモジュールのProjectを入れるソリューションフォルダー（既定 LinkedProjects）"] = "",
    external_folder: Annotated[str, "CMake・GoogleTest 等、自分で作っていないものを入れるソリューションフォルダー（既定 External）"] = "",
    msvc_runtime: Annotated[str, "MSVCのCランタイム（dll＝/MD〔既定〕・static＝/MT）。このモジュールを頂点にしたビルド全体に効く"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """モジュール全体の設定を変えます。

    main・ソリューションフォルダー・MSVCのCランタイムのうち、変えるものだけをオプションで渡します。管理ファイルが変わるので、タスクブランチでコミットしてください。

    例：
      ecobuild module settings set --main Core
      ecobuild module settings set --msvc-runtime static --linked-folder Linked
    """

    def action(inv):
        if not (main or no_main or projects_folder or linked_folder or external_folder or msvc_runtime):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "変えるものがありません。",
                                hint="--main・--no-main・--msvc-runtime・--projects-folder・--linked-folder・--external-folder の"
                                     "どれかを渡してください（今の設定は ecobuild module settings）。")
        return inv.module.set_module_settings(main=main or None, clear_main=no_main, msvc_runtime=msvc_runtime or None,
                                              projects_folder=projects_folder or None,
                                              linked_folder=linked_folder or None,
                                              external_folder=external_folder or None)

    return run_command("module settings set", action, render, json_output=json)
