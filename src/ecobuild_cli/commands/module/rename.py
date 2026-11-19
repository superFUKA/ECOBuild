import os
from pathlib import Path
from typing import Annotated

from ... import _log
from ..._output import lines, run_command


def command(
    new_name: Annotated[str, "新しいモジュール名（GitHub のリポジトリ名にもなる。英字で始まる英数字と _）"],
    dry_run: Annotated[bool, "変えるものを表示するだけ（何も変えない）"] = False,
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """モジュールの名前を変えます（GitHub のリポジトリ名・手元のフォルダー名・中の名前をまとめて）。

    順に：作成元のブランチ（main 等）で ecobuild.toml の名前・.ecobuild/README.md・AGENTS.md・CI のワークフロー・型の名前
    （C++ は Solution 名だけ。Project 名・include/<名前>/ は変えない。Python はパッケージ名も：pyproject の name・scripts、
    src/<小文字>/、import、tests/test_<小文字>.py）を「モジュールの改名」としてコミット → GitHub のリポジトリの名前を変える →
    手元の origin（作業空間も・このPCのほかの clone も）→ そのコミットを作成元へ push → 元の clone のフォルダーの名前が
    モジュール名なら、新しい名前へ移す（作業空間も一緒に動く）。ルートの README は変えません。
    移すと、ビルドの構成（C++ の build/）・仮想環境（Python の .venv）・コンテナは作り直しになります（消します）。
    Claude Code の会話の一覧は前の場所のものなので、移した先には出ません。
    依存元（このモジュールを使うほかのモジュール）は、そちらで ecobuild deps update すると新しい名前に直ります。
    できるのは管理者だけです。未コミットの変更・使用中の作業空間があるときは止まります。フォルダーを移すときは、移すフォルダー
    の外から実行してください（ecobuild -C <今の名前> module rename <新しい名前>。シェルが中にいると移せません）。
    途中で止まったら、直してからもう一度同じコマンドを実行すると、続きから行います。
    """

    def action(inv):
        module = inv.module
        preview = module.rename(new_name, dry_run=True)
        if dry_run:
            return preview
        inv.confirm(_question(preview))
        if preview.new_root is not None and Path.cwd().resolve().is_relative_to(preview.root.resolve()):
            os.chdir(preview.root.parent)   # このコマンドの今のフォルダーは移せないので、外へ出る
        result = module.rename(new_name, progress=inv.info)
        if result.moved and result.new_root is not None:
            _log.use_module(result.new_root)   # 続きのログは移した先のモジュールへ
        return result

    def render(r):
        if r.dry_run:
            return lines(f"モジュール {r.name} を {r.new_name} にします。変えるもの：", *("  " + t for t in _plan(r)))
        if not (r.github or r.origins or r.commit or r.moved):
            return f"モジュール {r.new_name} は、もう新しい名前です（変えるものはありません）"
        return lines(
            f"モジュール {r.name} を {r.new_name} にしました",
            f"GitHub のリポジトリ：{r.repository} → {r.new_repository}" if r.github else None,
            *(f"origin を新しい URL にしました：{c}" for c in r.origins),
            (f"「モジュールの改名」として {r.branch} にコミットしました（{r.commit[:8]}）"
             + ("。GitHub へ push しました" if r.pushed else "")) if r.commit else None,
            f"フォルダーを移しました：{r.root} → {r.new_root}" if r.moved else None,
            *r.cleaned,
            "作業空間のタスクブランチは、ecobuild sync で新しい名前を取り込みます" if r.workspaces else None,
            "依存元（このモジュールを使うモジュール）は、そちらで ecobuild deps update すると新しい名前に直ります",
            f"cd \"{r.new_root}\" で移った先へ" if r.moved else None,
        )

    return run_command("module rename", action, render, json_output=json, yes=yes)


def _plan(r) -> list[str]:
    found = []
    if r.github:
        found.append(f"GitHub のリポジトリ：{r.repository} → {r.new_repository}")
    found += [f"origin：{c}" for c in r.origins]
    if r.paths:
        found.append(f"{r.branch} にコミットするファイル：" + "、".join(r.paths))
    if r.new_root is not None:
        found.append(f"フォルダー：{r.root} → {r.new_root}（作業空間 {len(r.workspaces)} 個も一緒に。ビルドの構成・仮想環境・"
                     "コンテナは作り直し）")
    else:
        found.append(f"フォルダー：{r.root} はそのまま（名前がモジュール名と違うため）")
    return found


def _question(preview) -> str:
    return (f"モジュール {preview.name} の名前を {preview.new_name} に変えますか？\n" + "\n".join("  " + t for t in _plan(preview))
            + "\n（GitHub の名前を変えると、ほかの人の clone は GitHub の転送で使えますが、名前は変わります）")
