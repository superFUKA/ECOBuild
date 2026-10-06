from typing import Annotated

from ...module import Module
from .._output import lines, run_command


def command(
    name: Annotated[str, "モジュール名（GitHubのリポジトリ名にもなる）"],
    description: Annotated[str, "リポジトリの説明"] = "",
    public: Annotated[bool, "公開リポジトリにする（既定は非公開）"] = False,
    app: Annotated[bool, "mainだけの実行ファイルProjectも作る"] = False,
    owner: Annotated[str, "リポジトリの所有者（組織名など。既定はログイン中のユーザー）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """GitHubリポジトリとC++のSolution・Projectを作り、初回コミットをpushします。"""

    def action(inv):
        from ... import tooling
        module = Module.create(name, directory=inv.cwd, description=description, public=public,
                               app=app, owner=owner or tooling.load_config().get("owner"))
        inv.use_module(module)
        return module.summary()

    return run_command("new", action, lambda r: lines(
        f"モジュール {r.name} を作成しました：{r.root}",
        f"リポジトリ：{r.remote_url}",
        f"Project：{', '.join(r.projects)}",
    ), json_output=json)
