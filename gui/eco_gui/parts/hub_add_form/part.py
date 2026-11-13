"""モジュールを追加する窓の入力欄。方法を4つから選び（新規作成・GitHubから取得・手元のフォルダを登録・リポジトリをモジュールに）、
方法に合う欄だけを出す。入力のたびに、今の値をまとめて出す（実行するのは画面のボタン）。"""
from typing import Annotated


def part(
    types: Annotated[list[dict] | None, "モジュールの型（{name, new_kinds, default_new_kind}）。まだ読めていなければ null"] = None,
    candidates: Annotated[list[dict] | None, "GitHub にあるモジュール（{repository, type, private, updated, description, archived}）。まだなら null"] = None,
    modules: Annotated[list[dict], "この PC のモジュール（{path, repository}）。取得の候補から除く・保存先の初めの値に使う"] = [],
    owner: Annotated[str, "既定の所有者（所有者の欄の案内に出す）"] = "",
    problem: Annotated[str, "実行できなかった理由（窓の中に出す。入力した値は残る）"] = "",
    failed: Annotated[str, "実行できなかった理由の符号（登録したフォルダがモジュールでない not_in_module なら、「モジュールにする」を勧める）"] = "",
    picked: Annotated[str, "「参照…」で選んだフォルダ（届いたら、参照を押した欄に入れる）"] = "",
    picked_for: Annotated[str, "「参照…」を押した欄の名前"] = "",
) -> None: ...


def on_browse(
    field: Annotated[str, "「参照…」を押した欄（directory・folder・adopt_folder）"],
    initial: Annotated[str, "その欄の今の文字（選ぶ窓を、そこから開く）"] = "",
) -> None:
    if field not in ("directory", "folder", "adopt_folder"):
        raise ValueError("参照できる欄は directory・folder・adopt_folder です")


def on_changed(
    method: Annotated[str, "方法：new・clone・register・adopt"],
    directory: Annotated[str, "保存先の親フォルダ（new・clone）"] = "",
    name: Annotated[str, "モジュール名（new）"] = "",
    type: Annotated[str, "型（new）"] = "",
    kind: Annotated[str, "最初に作るもの（new。型にないなら空）"] = "",
    project: Annotated[str, "最初に作るものの名前（new。任意）"] = "",
    test: Annotated[bool | None, "テストも作るか（new でライブラリのときだけ。ほかは null）"] = None,
    description: Annotated[str, "説明（new。任意）"] = "",
    owner: Annotated[str, "所有者（new。任意）"] = "",
    public: Annotated[bool | None, "公開リポジトリにするなら true（しないなら null）"] = None,
    repository: Annotated[str, "GitHub のリポジトリ（clone）"] = "",
    folder: Annotated[str, "モジュールのフォルダ（register）"] = "",
    adopt_folder: Annotated[str, "リポジトリのフォルダ（adopt）"] = "",
    adopt_type: Annotated[str, "型（adopt）"] = "",
) -> None:
    if method not in ("new", "clone", "register", "adopt"):
        raise ValueError("方法は new・clone・register・adopt のどれかです")
