from typing import Annotated

from ...module import Module
from .._output import lines, run_command


def command(
    repository: Annotated[str, "GitHubのリポジトリ（名前、または 所有者/名前）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """GitHubにあるモジュールを今いるディレクトリへcloneし、依存先と生成ファイルを用意します。"""

    def action(inv):
        module, dependencies = Module.clone(repository, directory=inv.cwd)
        inv.use_module(module)
        return module.cloned(dependencies)

    return run_command("clone", action, lambda r: lines(
        f"モジュール {r.name} をcloneしました：{r.root}",
        f"リポジトリ：{r.remote_url}",
        "\n".join(f"  依存 {d.name}：{d.action}" for d in r.dependencies) or None,
    ), json_output=json)
