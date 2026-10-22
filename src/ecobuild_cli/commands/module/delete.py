import os
import sys
from pathlib import Path
from typing import Annotated

import click

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_cli._module import Module
from ..._module_target import find_clone, full_name
from ..._output import ask_text, lines, run_command


def command(
    name: Annotated[str, "モジュール名（GitHubのリポジトリ名。所有者/名前 も可）"],
    owner: Annotated[str, "リポジトリの所有者（組織名など。既定は設定の owner、なければログイン中のユーザー）"] = "",
    confirm: Annotated[str, "確認のため、削除するモジュールを 所有者/名前 でもう一度書く（端末では聞きます）"] = "",
    remove_workspaces: Annotated[bool, "手元の作業空間も削除する（このPCに記録したもの・今いるモジュール・"
                                       "今いるディレクトリの <名前>）"] = False,
    discard_local: Annotated[bool, "--remove-workspaces で、手元の作業空間にGitHubにない変更・コミット・退避があっても"
                                   "削除する（それらは失われます）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """アーカイブしたモジュール（GitHubのリポジトリ）を、Issue・PRとともに削除します。

    先に ecobuild module archive でアーカイブしたものだけを削除できます（2段階）。削除したリポジトリは、
    GitHubのアカウントの設定から90日以内なら元に戻せます。タスク管理の情報は消さずに閉じ、
    元に戻したときにそのまま使えるようにします。
    """

    def action(inv):
        if discard_local and not remove_workspaces:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--discard-local は --remove-workspaces と一緒に使います。")
        target = full_name(name, owner)
        clone = find_clone(inv, target)
        preview = Module.delete(target, clone=clone, remove_workspaces=remove_workspaces, discard_local=discard_local,
                                dry_run=True)
        _require_delete_permission(inv)
        _confirm(inv, _question(preview, remove_workspaces, discard_local), preview.repository, confirm)
        for root in preview.workspaces if remove_workspaces else ():
            if Path.cwd().resolve().is_relative_to(root.resolve()):
                os.chdir(root.parent)   # 今いるディレクトリは消せないので、外へ出る
        return Module.delete(target, clone=clone, remove_workspaces=remove_workspaces, discard_local=discard_local)

    def render(r):
        workspaces = [(f"作業空間 {c} の中身を削除しました（空のフォルダーは、端末等が使っているため残っています。"
                       "閉じてから削除してください）" if c.exists() else f"作業空間 {c} を削除しました") if c in r.removed else
                      f"作業空間 {c} は、他のプログラムが使っているため削除できませんでした。"
                      "閉じてからフォルダーを削除してください" if remove_workspaces else
                      f"作業空間 {c} は残しています（不要なら ecobuild workspace close {c} で閉じられます）"
                      for c in r.workspaces]
        return lines(f"モジュール {r.repository} を削除しました（GitHubのアカウントの設定から、90日以内なら元に戻せます）",
                     f"リポジトリ：{r.url}", *workspaces)

    return run_command("module delete", action, render, json_output=json)


def _question(preview, remove_workspaces: bool, discard_local: bool = False) -> str:
    text = (f"GitHubのモジュール {preview.repository}（開いているIssue {preview.open_issues} 件・"
            f"PR {preview.open_pull_requests} 件）を削除します。このモジュールを依存先にしているモジュールは、"
            "clone・sync ができなくなります。")
    if remove_workspaces and preview.workspaces:
        text += f"手元の作業空間 {'、'.join(map(str, preview.workspaces))} も削除します。"
        if discard_local:
            text += "GitHubにない変更・コミット・退避があっても、それらごと削除します。"
    return text


def _confirm(inv, question: str, repository: str, given: str) -> None:
    """名前をもう一度書いてもらう（取り違え・打ち間違いで、別のモジュールを消さないように）。"""
    if given:
        if given.casefold() != repository.casefold():
            raise EcoBuildError(ErrorCode.CONFIRMATION_REQUIRED,
                                f"--confirm の {given} が、削除するモジュール {repository} と違います。",
                                hint=f"所有者/名前 で書いてください（--confirm {repository}）。")
        return
    if inv.json_output or not sys.stdin.isatty():
        raise EcoBuildError(ErrorCode.CONFIRMATION_REQUIRED, f"確認が必要です：{question}",
                            hint=f"内容を確認し、--confirm {repository} を付けて実行してください。")
    click.echo(question, err=True)
    typed = ask_text(f"削除するには {repository} と入力してください", option=f"--confirm {repository}", default="",
                     show_default=False)
    if typed.strip().casefold() != repository.casefold():
        raise click.Abort()


def _require_delete_permission(inv) -> None:
    """リポジトリの削除には、ghのログインに delete_repo の権限が要る（既定のログインにはない）。"""
    from ecobuild_bundle import tooling
    if tooling.gh_has_scope("delete_repo"):
        return
    if not inv.json_output and sys.stdin.isatty() and click.confirm(
            "GitHubへのログインに、リポジトリを削除する権限（delete_repo）がありません。追加しますか？（ブラウザで承認します）",
            default=True, err=True):
        if tooling.run_interactive(["gh", "auth", "refresh", "--scopes", "delete_repo"]):
            return
    raise EcoBuildError(ErrorCode.BOARD_PERMISSION,
                        "GitHubへのログインに、リポジトリを削除する権限（delete_repo）がありません。",
                        hint="端末で ecobuild module delete を実行すると、権限の追加を案内します"
                             "（gh auth refresh -s delete_repo でも追加できます）。")
