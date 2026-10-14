from dataclasses import replace
from typing import Annotated

from ..._output import lines, run_command, split_list, usage_error

SWITCH = {"on": True, "off": False}


def command(
    os: Annotated[str, "動かすOS（カンマ区切り：windows,linux。既定は型が決める。cpp：両方）"] = "",
    configuration: Annotated[str, "ビルドする構成（カンマ区切り。例：Debug,Release。既定：Debug）"] = "",
    shared: Annotated[str, "ライブラリを共有ライブラリにした構成でもビルド・テストする（on／off）"] = "",
    branches: Annotated[str, "pushでCIを動かすブランチ（カンマ区切り。例：main,develop。既定：default_base。PRでは常に動く）"] = "",
    force: Annotated[bool, "手で編集したワークフローでも上書きする"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """CIのワークフローを作ります（作り直します）。

    ワークフロー（GitHub Actions）の中身はモジュールの型が用意します（cpp：構成・ビルド・テスト）。
    指定した項目は ecobuild.toml の [ci] に保存し、指定しなかった項目は保存してある設定のままにします。
    """
    if shared and shared not in SWITCH:
        return usage_error("--shared は on か off を指定してください。", json)

    def action(inv):
        module = inv.module
        settings = module.config.ci
        if os:
            settings = replace(settings, os=split_list(os))
        if configuration:
            settings = replace(settings, configurations=split_list(configuration))
        if shared:
            settings = replace(settings, shared=SWITCH[shared])
        if branches:
            settings = replace(settings, branches=split_list(branches))
        changed = settings != module.config.ci
        return module.write_ci(settings if changed else None, force=force)

    def render(r):
        return lines(
            f"{r.path} を作りました。作業空間でコミットし、PRで反映すると動きます",
            (f"注意：非公開の依存先（{', '.join(r.private_dependencies)}）は、CIの GITHUB_TOKEN では取得できません。"
             "それを読めるトークン（例：対象リポジトリの Contents を読めるだけの fine-grained token）を作り、"
             "このリポジトリのシークレット ECOBUILD_DEPS_TOKEN に登録してください"
             "（ecobuild ci secret set ECOBUILD_DEPS_TOKEN）。") if r.private_dependencies else None,
        )

    return run_command("ci init", action, render, json_output=json)
