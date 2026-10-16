from typing import Annotated

from ecobuild_bundle import Module
from ..._output import lines, run_command


def command(
    name: Annotated[str, "モジュール名（GitHubのリポジトリ名にもなる）"],
    description: Annotated[str, "リポジトリの説明"] = "",
    public: Annotated[bool, "公開リポジトリにする（既定は非公開）"] = False,
    kind: Annotated[str, "最初に作るもの（cpp・python：app＝実行できるもの〔既定〕・library＝ライブラリとテスト・none＝作らない）"] = "",
    project: Annotated[str, "最初に作るProjectの名前（既定はモジュール名。C++でライブラリならテスト用は <名前>Test。Python ではパッケージ名で、既定はモジュール名の小文字）"] = "",
    owner: Annotated[str, "リポジトリの所有者（組織名など。既定はログイン中のユーザー）"] = "",
    type: Annotated[str, "モジュールの型（ecobuild module types で一覧。既定は cpp）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """モジュール（GitHubリポジトリ）を作り、初回コミットをpushします。

    中身はモジュールの型が作ります（Python：pyproject.toml・src/<パッケージ>・tests）。
    C++では最初のProjectを1つ作ります（既定は実行ファイル。--kind で選べます）。名前は既定でモジュール名で、
    --project で変えられます。Projectは後から
    ecobuild project add で足せます。他のモジュールからリンクされるのは、最初に作ったProjectだけです
    （ライブラリのとき）。
    """

    def action(inv):
        from ecobuild import tooling
        module = Module.create(name, directory=inv.cwd, description=description, public=public,
                               kind=kind, project=project, owner=owner or tooling.load_config().get("owner"), type=type or None)
        inv.use_module(module)
        return module.summary()

    return run_command("module new", action, lambda r: lines(
        f"モジュール {r.name} を作成しました：{r.root}",
        f"リポジトリ：{r.remote_url}",
        f"Project：{', '.join(r.projects)}" if r.projects else "Project：なし（ecobuild project add で足せます）",
    ), json_output=json)
