from typing import Annotated

from ecobuild_cli.kit import run_command


def command(
    repository: Annotated[str, "リンクするモジュールのGitHubのリポジトリ（名前、または 所有者/名前）"],
    project: Annotated[str, "リンクするProject（既定：今いるProject、テスト用を除いてProjectが1つならそれ）"] = "",
    library: Annotated[str, "相手のモジュールのどのライブラリにリンクするか（既定：相手の main。一覧は deps libraries）"] = "",
    shared: Annotated[bool, "共有ライブラリとしてリンクする（既定は静的）"] = False,
    at: Annotated[str, "リンクする版（ブランチ・タグ・コミット。既定：既定のブランチの最新）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """GitHubにあるECOBuildのモジュールを依存先に加え（リンクし）、deps/ へcloneします。

    タスクブランチで行い、変えた ECOBuild のファイル（.ecobuild の中）は、このリンクとしてコミットします（Push はしません）。

    リンクするのは、相手のモジュールのライブラリのうち --library で選んだもの（省くと main：相手で最初に作ったライブラリ）です。
    選べるものは ecobuild deps libraries <リポジトリ> で表示できます。既にある依存先の別のライブラリにも、もう一度 deps add で
    リンクを足せます（記録の版のまま）。

    例：
      ecobuild deps add Math
      ecobuild deps add owner/Engine --library Physics --shared
    """

    def action(inv):
        module = inv.module
        from ecobuild import settings
        return module.link(settings.qualify(repository), project=project or module.project_at(inv.cwd), shared=shared,
                           revision=at or None, library=library or None)

    return run_command("deps add", action, _text, json_output=json)


def _text(result) -> str:
    target = f"{result.name} の {result.libraries[0]}" if result.libraries else result.name
    text = f"{result.projects[0]} に {target}（{result.revision[:7]}）をリンクしました：deps/{result.name}"
    clone = result.clone
    if clone is not None and clone.action == "aligned":
        text += f"\n既にあった deps/{result.name} を、記録した版に合わせました。"
    elif clone is not None and clone.action == "skipped":
        text += (f"\n既にあった deps/{result.name} は記録した版と違いますが、合わせていません：{clone.reason}"
                 "\n（記録の版を使うには、作業を片付けてから ecobuild deps sync）")
    return text
