from typing import Annotated

from ecobuild_cli.kit import run_command


def command(
    repository: Annotated[str, "リンクするモジュールのGitHubのリポジトリ（名前、または 所有者/名前）"],
    project: Annotated[str, "リンクするProject（既定：今いるProject、テスト用を除いてProjectが1つならそれ）"] = "",
    shared: Annotated[bool, "共有ライブラリとしてリンクする（既定は静的）"] = False,
    at: Annotated[str, "リンクする版（ブランチ・タグ・コミット。既定：既定のブランチの最新）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """GitHubにあるECOBuildのモジュールを依存先に加え（リンクし）、deps/ へcloneします。

    タスクブランチで行い、変えた ECOBuild のファイル（.ecobuild の中）は、このリンクとしてコミットします（Push はしません）。

    リンクされるのは、相手のモジュールで最初に作ったProjectです（ライブラリである必要があります）。
    """

    def action(inv):
        module = inv.module
        from ecobuild import settings
        return module.link(settings.qualify(repository), project=project or module.project_at(inv.cwd), shared=shared,
                           revision=at or None)

    return run_command("deps add", action, _text, json_output=json)


def _text(result) -> str:
    text = f"{result.projects[0]} に {result.name}（{result.revision[:7]}）をリンクしました：deps/{result.name}"
    clone = result.clone
    if clone is not None and clone.action == "aligned":
        text += f"\n既にあった deps/{result.name} を、記録した版に合わせました。"
    elif clone is not None and clone.action == "skipped":
        text += (f"\n既にあった deps/{result.name} は記録した版と違いますが、合わせていません：{clone.reason}"
                 "\n（記録の版を使うには、作業を片付けてから ecobuild deps sync）")
    return text
