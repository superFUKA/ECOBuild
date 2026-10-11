import os
import sys
from pathlib import Path
from typing import Annotated

import click

from ecowork import WorkError

from ...errors import EcoBuildError, ErrorCode
from ...module import Module
from .._output import lines, run_command


def command(
    repository: Annotated[str, "削除するモジュール（GitHubのリポジトリ名、または 所有者/名前）"],
    archive: Annotated[bool, "削除せず、アーカイブ（読み取り専用。GitHubで元に戻せる）にする"] = False,
    remove_clone: Annotated[bool, "今いる（-C で指定した）モジュールの手元のcloneも削除する"] = False,
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """モジュール（GitHubのリポジトリ）を、Issue・PR・タスク管理の情報とともに削除します（元に戻せません）。

    ECOBuildのモジュールだけを扱います。残しておくなら --archive（読み取り専用にし、後から元に戻せます）。
    """
    kept = []   # 削除しなかった手元のclone

    def action(inv):
        from ... import tooling
        name = tooling.qualify(repository)
        clone = inv.module if remove_clone else None
        preview = Module.delete(name, archive=archive, clone=clone, dry_run=True)
        if not archive:
            _require_delete_permission(inv)
        inv.confirm(_question(preview))
        if clone is None:
            if not archive:
                kept.extend(_clone_here(inv, preview.repository))
        elif Path.cwd().resolve().is_relative_to(clone.root.resolve()):
            os.chdir(clone.root.parent)   # 今いるディレクトリは消せないので、外へ出る
        return Module.delete(name, archive=archive, clone=clone)

    return run_command("delete", action, lambda r: lines(
        f"モジュール {r.repository} をアーカイブしました（読み取り専用。GitHubのリポジトリの設定から元に戻せます）"
        if r.archived else
        f"モジュール {r.repository} を削除しました{'（タスク管理の情報も削除しました）' if r.task_data else ''}",
        (f"手元のclone {r.clone} を削除しました" if r.clone_removed else
         f"手元のclone {r.clone} は、他のプログラムが使っているため削除できませんでした。閉じてからフォルダーを削除してください")
        if r.clone else None,
        *(f"手元のclone {path} は残しています（不要ならフォルダーを削除してください）" for path in kept),
    ), json_output=json, yes=yes)


def _question(preview) -> str:
    counts = f"（開いているIssue {preview.open_issues} 件・PR {preview.open_pull_requests} 件）"
    if preview.archived:
        text = f"GitHubのモジュール {preview.repository}{counts} をアーカイブ（読み取り専用）にします。"
    else:
        extra = "と、そのタスク管理の情報" if preview.task_data else ""
        text = f"GitHubのモジュール {preview.repository}{counts}{extra}を削除します。元に戻せません。"
    if preview.clone is not None:
        text += f"手元のclone {preview.clone} も削除します。"
    return text + "よろしいですか？"


def _require_delete_permission(inv) -> None:
    """リポジトリの削除には、ghのログインに delete_repo の権限が要る（既定のログインにはない）。"""
    from ... import tooling
    if tooling.gh_has_scope("delete_repo"):
        return
    if not inv.json_output and sys.stdin.isatty() and click.confirm(
            "GitHubへのログインに、リポジトリを削除する権限（delete_repo）がありません。追加しますか？（ブラウザで承認します）",
            default=True, err=True):
        if tooling.run_interactive(["gh", "auth", "refresh", "--scopes", "delete_repo"]):
            return
    raise EcoBuildError(ErrorCode.BOARD_PERMISSION,
                        "GitHubへのログインに、リポジトリを削除する権限（delete_repo）がありません。",
                        hint="端末で ecobuild delete を実行すると、権限の追加を案内します"
                             "（gh auth refresh -s delete_repo でも追加できます）。")


def _clone_here(inv, repository: str) -> list[Path]:
    """今いるディレクトリが、削除するモジュールのcloneなら、そのパス（削除後も残ることを知らせる）。"""
    try:
        module = inv.module
    except WorkError:      # モジュールの外
        return []
    here = module.repository.github.repository_name(module.root)
    return [module.root] if here.casefold() == repository.casefold() else []
