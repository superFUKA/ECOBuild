import os
from pathlib import Path
from typing import Annotated

from ecobuild import workspaces as _workspaces
from ecobuild_cli._module import Module
from ..._output import lines, optional_argument, run_command


def render_closed(r) -> str:
    """作業空間を閉じた結果（workspace close）。"""
    if not r.done:
        return f"作業空間 {r.path} を閉じられます（GitHubにないものはありません）"
    if r.removed:
        return f"作業空間 {r.path} を閉じました（場所ごと削除しました）"
    if r.left:
        return (f"作業空間 {r.path} を閉じました。他のプログラムが使っているものが残っています（{'、'.join(r.left)}）。"
                "閉じてからフォルダーを削除してください")
    return (f"作業空間 {r.path} を閉じました（中身を削除しました。空のフォルダーは、端末等が使っているため残っています。"
            "閉じてから削除してください）")


def render_removed(r) -> str | None:
    """タスクの操作（finish・drop・close・prune 等）で、タスクブランチと一緒に作業空間を消した・残したこと。"""
    if getattr(r, "workspace_removed", None):
        return f"作業空間 {r.workspace_removed} を消しました"
    if getattr(r, "workspace_kept", None):
        return f"作業空間を残しました（{r.workspace_kept}）"
    return None


def leave(root: Path, inv=None) -> None:
    """今いるディレクトリが作業空間 root の中なら、外（元の clone。前の版の作業空間なら親）へ出る（このプロセスが
    使っている場所は消せないため）。inv：コマンドが終わったとき、元の場所がまだあれば戻る（消さなかったとき・失敗したとき）。"""
    root = Path(root).resolve()
    here = Path.cwd()
    if not here.resolve().is_relative_to(root):
        return
    original = _workspaces.original_of(root).resolve()
    os.chdir(original if original != root else root.parent)
    if inv is not None:
        inv.holds.callback(lambda: here.is_dir() and os.chdir(here))


def command(
    *path: Annotated[str, "閉じる作業空間の場所（--at と同じ）"],
    at: Annotated[str, "閉じる作業空間の場所（既定は今いる作業空間）"] = "",
    discard_local: Annotated[bool, "GitHubにない変更・新しいファイル・コミット・退避があっても閉じる（それらは失われます）"] = False,
    dry_run: Annotated[bool, "閉じられるかを確かめるだけ"] = False,
    yes: Annotated[bool, "確認せずに実行する（--discard-local のとき）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """作業空間を閉じます：場所ごと削除します。GitHubのリポジトリ・ブランチ・タスクには触りません。

    閉じられるのは、元の clone の中の作業空間（.ecobuild/w/<名前>）と、前の版の作業空間（独立した clone。記録からも
    外します）です。元の clone は閉じられません。GitHubにないもの（未コミットの変更・新しいファイル・コミット・退避。
    依存先のcloneも）があれば止まります。除外したファイル（ビルドの出力・このPC用の設定・ログ）は一緒に消えます。
    タスクの作業空間は、ふだんは task finish・drop・close でタスクブランチと一緒に消えます。
    """
    target = optional_argument(path, at, "--at", json)

    def action(inv):
        root = Path(inv.cwd / target) if target else inv.module.root
        preview = Module.close_workspace(root, discard_local=discard_local, dry_run=True)
        if dry_run:
            return preview
        if discard_local:
            inv.confirm(f"作業空間 {preview.path} を、GitHubにないものも含めて削除しますか？")
        leave(preview.path, inv)
        return Module.close_workspace(preview.path, discard_local=discard_local)

    return run_command("workspace close", action, lambda r: lines(render_closed(r)), json_output=json, yes=yes)
