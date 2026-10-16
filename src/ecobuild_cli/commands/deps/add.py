from typing import Annotated

from ..._output import run_command


def command(
    repository: Annotated[str, "リンクするモジュールのGitHubのリポジトリ（名前、または 所有者/名前）"],
    project: Annotated[str, "リンクするProject（既定：今いるProject、テスト用を除いてProjectが1つならそれ）"] = "",
    shared: Annotated[bool, "共有ライブラリとしてリンクする（既定は静的）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """GitHubにあるECOBuildのモジュールを依存先に加え（リンクし）、deps/ へcloneします。

    管理ファイルが変わるので、作業空間でコミットしてください。

    リンクされるのは、相手のモジュールで最初に作ったProjectです（ライブラリである必要があります）。
    """

    def action(inv):
        module = inv.module
        from ecobuild import settings
        return module.link(settings.qualify(repository), project=project or module.project_at(inv.cwd), shared=shared)

    return run_command("deps add", action,
                       lambda r: f"{r.projects[0]} に {r.name}（{r.revision[:7]}）をリンクしました：deps/{r.name}",
                       json_output=json)
