"""C++ のモジュールのページ：Project・依存先・全般・ファイルテンプレートの表（view で、どれを描くかを決める）。

- projects：Project の木（テスト・性能測定は、リンクするライブラリの下に段を付ける。main の印、種類の印、場所、リンクの印＝依存先は緑）と凡例。
  行に「設定…」と ⋯（リンクを足す…・リンクを外す…・PCH…・移動…・削除…）。
- deps：依存先の表（記録の版・手元の版・状態の印：記録の版＝緑／別の版・未コミットの変更＝黄／clone なし＝赤。GitHub と照らし合わせた列、
  使っている Project）と、依存関係の図（依存先の依存先も。「上に同じ」「clone なし」の印）。版を選ぶ所（タグ・コミットの新しい順）。
- general：ほかのモジュールからリンクされる Project（main）・MSVC の C ランタイム・ソリューションフォルダー。
- templates：ファイルテンプレート（既定の印）。

見せ方だけ。押した操作は action で出す（何が起きるかは、つないだコマンドと、開く入力の窓が決める）。
"""
from typing import Annotated, Literal


def part(
    view: Annotated[Literal["projects", "deps", "general", "templates"], "描くもの"],
    projects: Annotated[list[dict], "Project（ecobuild project list：name・kind・directory・links）"] = [],
    deps: Annotated[list[dict], "依存先（ecobuild deps list：name・url・recorded・local・branch・state。--fetch なら remote・moved_to・latest も）"] = [],
    tree: Annotated[dict | None, "依存関係（ecobuild deps tree：module・direct・nodes）"] = None,
    settings: Annotated[dict | None, "モジュールの設定（ecobuild module settings：main_project・msvc_runtime・folders・templates）"] = None,
    fetched: Annotated[bool | None, "依存先を GitHub と照らし合わせて読んだか（列を足す）"] = False,
    versions: Annotated[dict | None, "選べる版（ecobuild deps versions：name・recorded・branch・branches・default_branch・tags・commits）。読むまで null"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_action(
    name: Annotated[str, "押した操作：project_add・project_settings・project_link・project_unlink・project_pch・project_move・project_remove／"
                         "deps_fetch・deps_sync・deps_update・dep_add・dep_update・dep_versions・dep_use・dep_versions_close・dep_remove／"
                         "module_settings／template_add・template_replace・template_remove"],
    target: Annotated[str, "対象の名前（Project・依存先・テンプレート）"] = "",
    value: Annotated[str, "dep_versions：ブランチ（空なら既定）／dep_use：版（タグの名前かコミット）"] = "",
) -> None:
    if not name:
        raise ValueError("操作の名前が要ります")


def on_reload() -> None: ...
