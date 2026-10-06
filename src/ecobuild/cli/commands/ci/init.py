from typing import Annotated

from ..._output import lines, run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """GitHub Actions のワークフロー（Windows・Linuxで、CMakeだけで構成・ビルド・テスト）を作ります。"""
    def render(r):
        return lines(
            f"{r.path} を作りました。作業空間でコミットし、PRで反映すると動きます",
            (f"注意：非公開の依存先（{', '.join(r.private_dependencies)}）は、CIの GITHUB_TOKEN では取得できません。"
             "それを読めるトークン（例：対象リポジトリの Contents を読めるだけの fine-grained token）を作り、"
             "このリポジトリのシークレット ECOBUILD_DEPS_TOKEN に登録してください"
             "（gh secret set ECOBUILD_DEPS_TOKEN）。") if r.private_dependencies else None,
        )

    return run_command("ci init", lambda inv: inv.module.write_ci(), render, json_output=json)
