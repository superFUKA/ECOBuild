import os
from pathlib import Path
from typing import Annotated

from ecobuild_cli._module import Module
from ..._output import lines, optional_argument, run_command


def render_closed(r) -> str:
    """作業空間を閉じた結果（workspace close・task finish --close-workspace）。"""
    if not r.done:
        return f"作業空間 {r.path} を閉じられます（GitHubにないものはありません）"
    if r.removed:
        return f"作業空間 {r.path} を閉じました（場所ごと削除しました）"
    if r.left:
        return (f"作業空間 {r.path} を閉じました。他のプログラムが使っているものが残っています（{'、'.join(r.left)}）。"
                "閉じてからフォルダーを削除してください")
    return (f"作業空間 {r.path} を閉じました（中身を削除しました。空のフォルダーは、端末等が使っているため残っています。"
            "閉じてから削除してください）")


def leave(root: Path) -> None:
    """今いるディレクトリがその作業空間の中なら、外へ出る（このプロセスが使っている場所は消せないため）。"""
    if Path.cwd().resolve().is_relative_to(Path(root).resolve()):
        os.chdir(Path(root).resolve().parent)


def command(
    *path: Annotated[str, "閉じる作業空間の場所（--at と同じ）"],
    at: Annotated[str, "閉じる作業空間の場所（既定は今いる作業空間）"] = "",
    discard_local: Annotated[bool, "GitHubにない変更・新しいファイル・コミット・退避があっても閉じる（それらは失われます）"] = False,
    dry_run: Annotated[bool, "閉じられるかを確かめるだけ"] = False,
    yes: Annotated[bool, "確認せずに実行する（--discard-local のとき）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """作業空間を閉じます：場所ごと削除し、このPCの記録から外します。GitHubのリポジトリ・タスクには触りません。

    GitHubにないもの（未コミットの変更・新しいファイル・コミット・退避。依存先のcloneも）があれば止まります。
    除外したファイル（ビルドの出力・このPC用の設定・ログ）は一緒に消えます。タスクの完了と一緒に閉じるなら
    ecobuild task finish --close-workspace。
    """
    target = optional_argument(path, at, "--at", json)

    def action(inv):
        root = Path(inv.cwd / target) if target else inv.module.root
        preview = Module.close_workspace(root, discard_local=discard_local, dry_run=True)
        if dry_run:
            return preview
        if discard_local:
            inv.confirm(f"作業空間 {preview.path} を、GitHubにないものも含めて削除しますか？")
        leave(preview.path)
        return Module.close_workspace(preview.path, discard_local=discard_local)

    return run_command("workspace close", action, lambda r: lines(render_closed(r)), json_output=json, yes=yes)
