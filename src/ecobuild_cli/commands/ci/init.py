from dataclasses import replace
from typing import Annotated

from ecobuild import ci_review
from ecobuild.config import CI_REVIEW_AUTH

from ..._output import lines, run_command, split_list, usage_error

SWITCH = {"on": True, "off": False}


def command(
    os: Annotated[str, "動かすOS（カンマ区切り：windows,linux。既定は型が決める。cpp：両方、generic・python：linux）"] = "",
    configuration: Annotated[str, "ビルドする構成（カンマ区切り。例：Debug,Release。既定：Debug）"] = "",
    shared: Annotated[str, "ライブラリを共有ライブラリにした構成でもビルド・テストする（on／off）"] = "",
    branches: Annotated[str, "pushでCIを動かすブランチ（カンマ区切り。例：main,develop。既定：default_base。PRでは常に動く）"] = "",
    review: Annotated[str, "提出（PR）を Claude が見直し、PR のコメントに書く（on／off）"] = "",
    review_auth: Annotated[str, "見直しの認証（subscription：Claude の契約のトークン CLAUDE_CODE_OAUTH_TOKEN、"
                                "api-key：API キー ANTHROPIC_API_KEY）"] = "",
    force: Annotated[bool, "手で編集したワークフローでも上書きする"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """CIのワークフローを作ります（作り直します）。

    ワークフロー（GitHub Actions）の中身はモジュールの型が用意します（cpp：構成・ビルド・テスト、python：pip・pytest）。
    指定した項目は ecobuild.toml の [ci] に保存し、指定しなかった項目は保存してある設定のままにします。

    --review on で、提出（PR）が出た・更新されたときに Claude が見直すワークフロー（.github/workflows/ecobuild-review.yml）
    も作ります。タスク（Issue）の完了の条件・REVIEW.md の観点と差分を比べ、足りない所・誤りを PR のコメントに書きます
    （助言なので、取り込みは止めず、承認にも数えません）。
    """
    for name, value in (("--shared", shared), ("--review", review)):
        if value and value not in SWITCH:
            return usage_error(f"{name} は on か off を指定してください。", json)
    if review_auth and review_auth not in CI_REVIEW_AUTH:
        return usage_error(f"--review-auth は {' か '.join(CI_REVIEW_AUTH)} を指定してください。", json)

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
        if review:
            settings = replace(settings, review=SWITCH[review])
        if review_auth:
            settings = replace(settings, review_auth=review_auth)
        changed = settings != module.config.ci
        return module.write_ci(settings if changed else None, force=force)

    def render(r):
        return lines(
            f"{r.path} を作りました。タスクブランチでコミットし、PRで反映すると動きます",
            *_review_lines(r),
            (f"注意：非公開の依存先（{', '.join(r.private_dependencies)}）は、CIの GITHUB_TOKEN では取得できません。"
             "それを読めるトークン（例：対象リポジトリの Contents を読めるだけの fine-grained token）を作り、"
             "このリポジトリのシークレット ECOBUILD_DEPS_TOKEN に登録してください"
             "（ecobuild ci secret set ECOBUILD_DEPS_TOKEN）。") if r.private_dependencies else None,
        )

    return run_command("ci init", action, render, json_output=json)


def _review_lines(r) -> list[str]:
    if r.removed:
        return [f"見直しをやめました（{', '.join(r.removed)} を消しました）"]
    if not r.review_path:
        return []
    return [f"{r.review_path}（提出を Claude が見直す）も作りました。使うには（どちらもリポジトリの管理者が1回だけ）：",
            f"  1. Claude の GitHub App をこのリポジトリに入れる：{ci_review.APP_URL}",
            f"  2. シークレット {r.review_secret} を登録する：ecobuild ci secret set {r.review_secret}"
            + ("（まだ登録されていません）" if r.review_secret_missing else "（登録済みなら不要）"),
            f"見直しの観点は、モジュールのルートの {ci_review.REVIEW_GUIDE} に書けます（任意）"]
