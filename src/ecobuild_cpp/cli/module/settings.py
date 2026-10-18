from typing import Annotated

from ecobuild_cli.kit import lines, run_command


def render(r: dict) -> str:
    folders = r["folders"]
    custom = [f"  {name} → {folder}" for name, folder in (folders or {}).get("project_folders", {}).items()]
    return lines(
        f"他のモジュールからリンクされるProject（main）：{r['main_project'] or 'なし'}",
        "ソリューションフォルダー：使わない" if folders is None else
        f"ソリューションフォルダー：自分のProject {folders['projects']}・リンク先 {folders['linked_projects']}"
        f"・外部 {folders['external']}",
        ("Projectごとのフォルダー：\n" + "\n".join(custom)) if custom else None,
        f"MSVCのCランタイム：{r['msvc_runtime']}（{'/MD' if r['msvc_runtime'] == 'dll' else '/MT'}）",
        "ファイルテンプレート：" + ", ".join(r["templates"]) + "（ecobuild template list）",
    )


def command(
    main: Annotated[str, "他のモジュールからリンクされるProject（main）を変える（ライブラリであること）"] = "",
    no_main: Annotated[bool, "main をなしにする（他のモジュールからリンクできなくなる）"] = False,
    projects_folder: Annotated[str, "Visual Studio で自分のProjectを入れるソリューションフォルダー（既定 Projects）"] = "",
    linked_folder: Annotated[str, "リンク先のモジュールのProjectを入れるソリューションフォルダー（既定 LinkedProjects）"] = "",
    external_folder: Annotated[str, "CMake・GoogleTest 等、自分で作っていないものを入れるソリューションフォルダー（既定 External）"] = "",
    msvc_runtime: Annotated[str, "MSVCのCランタイム（dll＝/MD〔既定〕・static＝/MT）。このモジュールを頂点にしたビルド全体に効く"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """モジュール全体の設定（main・ソリューションフォルダー・MSVCのCランタイム）を表示します。オプションを付けると変えます。

    タスクブランチで行い、変わった ECOBuild のファイル（.ecobuild の中）はそのままコミットします（Push はしません）。Projectごとの設定は ecobuild project set、
    ビルドのたびに選ぶもの（構成・生成器・C++の規格等）は ecobuild profile で設定します。
    """

    def action(inv):
        module = inv.module
        if not (main or no_main or projects_folder or linked_folder or external_folder or msvc_runtime):
            return module.module_settings()
        return module.set_module_settings(main=main or None, clear_main=no_main, msvc_runtime=msvc_runtime or None,
                                          projects_folder=projects_folder or None,
                                          linked_folder=linked_folder or None,
                                          external_folder=external_folder or None)

    return run_command("module settings", action, render, json_output=json)
