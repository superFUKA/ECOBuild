"""ハブのモジュールの一覧。型ごとの見出しと件数、モジュールのカード（色付きの頭文字・名前・リポジトリ・状態の印・⋯ と右クリックのメニュー）、
アーカイブ済み・前の作業空間の折りたたみ、空のときの案内。並べ替え（同じ型の中でドラッグ）は、この PC に覚える。"""
from typing import Annotated


def part(
    rows: Annotated[list[dict] | None, "この PC のモジュール（{path, exists, repository, url, type}）。まだ読めていなければ null"] = None,
    legacy: Annotated[list[dict], "前の版が作った作業空間（{path, exists, repository, url, branch, task}）"] = [],
    known: Annotated[list[dict] | None, "GitHub にあるモジュール（{repository, type, archived, description}）。まだ読めていなければ null"] = None,
) -> None: ...


def on_action(
    id: Annotated[str, "モジュールのフォルダー"],
    action: Annotated[str, "すること：open（開く）・forget（一覧から外す）・away（片付ける）"],
    name: Annotated[str, "モジュールの名前"] = "",
    repository: Annotated[str, "GitHub のリポジトリ（所有者/名前）"] = "",
    reason: Annotated[str, "開けない理由（開けないモジュールを押したとき）"] = "",
) -> None:
    if not id or action not in ("open", "forget", "away"):
        raise ValueError("モジュールと、すること（open・forget・away）が要ります")


def on_add() -> None: ...


def on_archived(
    repository: Annotated[str, "GitHub のリポジトリ（所有者/名前）"],
    action: Annotated[str, "すること：unarchive（解除）・delete（削除）"],
    local: Annotated[str, "この PC にある clone のフォルダー（「、」でつないだもの）"] = "",
) -> None:
    if not repository or action not in ("unarchive", "delete"):
        raise ValueError("リポジトリと、すること（unarchive・delete）が要ります")


def on_legacy(
    path: Annotated[str, "前の作業空間のフォルダー"],
    action: Annotated[str, "すること：close（閉じる）・forget（一覧から外す）"],
) -> None:
    if not path or action not in ("close", "forget"):
        raise ValueError("フォルダーと、すること（close・forget）が要ります")
