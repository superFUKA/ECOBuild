from typing import Annotated

from .._output import run_command


def command(
    repository: Annotated[str, "リンクするモジュールのGitHubのリポジトリ（名前、または 所有者/名前）"],
    project: Annotated[str, "リンクするProject（既定：今いるProject、それ以外はライブラリ）"] = "",
    shared: Annotated[bool, "共有ライブラリとしてリンクする（既定は静的）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """GitHubにあるECOBuildのモジュールをリンクし、deps/ へcloneします。管理ファイルが変わるので、作業空間でコミットしてください。"""

    def action(inv):
        module = inv.module
        from ... import tooling
        return module.link(tooling.qualify(repository), project=project or module.project_at(inv.cwd), shared=shared)

    return run_command("link", action,
                       lambda r: f"{r.projects[0]} に {r.name}（{r.revision[:7]}）をリンクしました：deps/{r.name}",
                       json_output=json)
