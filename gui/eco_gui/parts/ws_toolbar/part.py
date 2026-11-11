"""作業空間の窓のツールバー。左に構成・ビルド設定、ビルド（▾ リビルド・クリーン・提出前の確認）、テスト（▾）、▶ 実行。

右に「取り込む」（作成元の名前・取り込み済みの版・遅れの数。遅れは黄、衝突の見込みは赤。▾ で選んで取り込む・最新を確認）、
アカウント（この作業空間だけのアカウントなら色が付く）、コンテナ（コンテナ／このPC）、エージェント。押したものは action で出す。"""
from typing import Annotated


def part(
    status: Annotated[dict, "状態（ecobuild status：task・base・base_at・behind・merging・reviewing）"] = {},
    remote: Annotated[dict, "GitHub の最新を確かめた状態（ecobuild status --fetch：base_behind・base_conflicts）"] = {},
    profiles: Annotated[dict, "ビルド設定（ecobuild profile list：profiles・selected）"] = {},
    configuration: Annotated[str | None, "この窓で選んでいる構成（空ならビルド設定のまま）"] = "",
    module_type: Annotated[str | None, "モジュールの型（cpp なら、構成に RelWithDebInfo・MinSizeRel も出す）"] = "",
    account: Annotated[dict, "アカウント（ecobuild account show：login・role・workspace_account）"] = {},
    container: Annotated[dict, "コンテナ（ecobuild container status：container・state・docker_ready・docker_detail・image）"] = {},
    last_test: Annotated[dict | None, "この窓で前に流した試験の結果（ecobuild test の result：cases）。失敗したものを「失敗だけ再実行」に出す"] = None,
) -> None: ...


def on_action(
    name: Annotated[str, "押したもの（build・rebuild・clean・check・test・test_failed・test_pick・run・sync・sync_pick・fetch・"
                         "configuration・profile・build_settings・account・container・agents）"],
    value: Annotated[str, "configuration：構成の名前（空ならビルド設定のまま）／profile：ビルド設定の名前（none なら使わない）"] = "",
    tests: Annotated[list[str], "test_failed：流す試験"] = [],
) -> None:
    if not name:
        raise ValueError("操作の名前が要ります")
