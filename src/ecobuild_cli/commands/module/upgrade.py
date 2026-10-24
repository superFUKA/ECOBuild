from typing import Annotated

from ..._output import lines, run_command


def command(
    dry_run: Annotated[bool, "変えるファイルを表示するだけ（何も変えない）"] = False,
    branch: Annotated[str, "今いるのでない管理用のブランチ（main・develop 等）を合わせる（手元の作業ツリーには触れない）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """モジュールを今の ECOBuild の仕様に合わせ、「ECOBuild の更新」としてコミットします。

    ecobuild.toml の format（仕様の版）を今の版にし、ECOBuild が作ったファイルを今の中身にします：.gitignore・.gitattributes（足りない行を足す）、.ecobuild/README.md
    （なければ置く）・AGENTS.md・CIのワークフロー（あれば作り直す。手で編集したワークフローはそのまま）、型の生成ファイル。
    ルートの README は変えません。
    どのブランチでもできます。タスクブランチでなければ GitHub へ push もします（タスクブランチなら、いつもの Push・提出で）。
    未コミットの変更があるときは止まります（変更が混ざらないように）。
    --branch <名前> を付けると、管理用のブランチ（作業空間で開かないブランチ）の GitHub の最新を、手元の作業ツリーに触れずに
    （一時的な作業ツリーで）合わせて、GitHub のそのブランチへ push します。できるのは、そのブランチへの提出を取り込める人です。
    """

    def render(r):
        version = (f"仕様の版 {r.format} → {r.latest_format}" if r.format != r.latest_format
                   else f"仕様の版 {r.latest_format}（今の版です）")
        changed = "\n".join(f"  {p}" for p in r.paths)
        if r.dry_run:
            head = f"{version}。変えるファイル：\n{changed}" if r.paths else f"{version}。変えるファイルはありません"
            return lines(head, *(f"手で編集してあるため作り直しません：{p}" for p in r.skipped))
        head = f"{version}。変えたファイル：\n{changed}" if r.paths else f"{version}。変えたファイルはありません"
        return lines(
            head,
            *(f"手で編集してあるため作り直していません：{p}（作り直すなら ecobuild ci init --force）" for p in r.skipped),
            (f"「ECOBuild の更新」として {r.branch} にコミットしました（{r.commit[:8]}）"
             + ("。GitHub へ push しました" if r.pushed else "。Push・提出はいつものとおり") if r.commit else None),
        )

    return run_command("module upgrade", lambda inv: inv.module.upgrade(dry_run=dry_run, branch=branch), render, json_output=json)
