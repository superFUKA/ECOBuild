"""モジュール全体の設定を扱います。

見るのは module settings、変えるのは module settings set（main・ソリューションフォルダー・MSVCのCランタイム）。"""

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


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュール全体の設定を表示します。

    main（他のモジュールからリンクされるProject）・ソリューションフォルダー・MSVCのCランタイムです。変えるのは ecobuild module settings set です。Projectごとの設定は ecobuild project set、
    ビルドのたびに選ぶもの（構成・生成器・C++の規格等）は ecobuild profile で設定します。
    """
    return run_command("module settings", lambda inv: inv.module.module_settings(), render, json_output=json)
