from typing import Annotated

from ....module import Module
from ..._output import lines, run_command


def command(
    name: Annotated[str, "モジュール名（GitHubのリポジトリ名にもなる）"],
    description: Annotated[str, "リポジトリの説明"] = "",
    public: Annotated[bool, "公開リポジトリにする（既定は非公開）"] = False,
    kind: Annotated[str, "最初に作るもの（C++：app＝実行ファイル〔既定〕・library＝ライブラリとテスト用・none＝作らない）"] = "",
    project: Annotated[str, "最初に作るProjectの名前（既定はモジュール名。ライブラリならテスト用は <名前>Test）"] = "",
    owner: Annotated[str, "リポジトリの所有者（組織名など。既定はログイン中のユーザー）"] = "",
    type: Annotated[str, "モジュールの型（ecobuild module types で一覧）"] = "cpp",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """モジュール（GitHubリポジトリ）を作り、初回コミットをpushします。

    C++では最初のProjectを1つ作ります（既定は実行ファイル。--kind で選べます）。名前は既定でモジュール名で、
    --project で変えられます。Projectは後から
    ecobuild project add で足せます。他のモジュールからリンクされるのは、最初に作ったProjectだけです
    （ライブラリのとき）。
    """

    def action(inv):
        from .... import tooling
        module = Module.create(name, directory=inv.cwd, description=description, public=public,
                               kind=kind, project=project, owner=owner or tooling.load_config().get("owner"), type=type)
        inv.use_module(module)
        return module.summary()

    return run_command("module new", action, lambda r: lines(
        f"モジュール {r.name} を作成しました：{r.root}",
        f"リポジトリ：{r.remote_url}",
        f"Project：{', '.join(r.projects)}" if r.projects else "Project：なし（ecobuild project add で足せます）",
    ), json_output=json)
