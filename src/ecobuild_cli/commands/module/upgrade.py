from typing import Annotated

from ..._output import lines, run_command


def command(
    dry_run: Annotated[bool, "変えるファイルを表示するだけ（何も変えない）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """モジュールを今の ECOBuild の仕様に合わせます（タスクブランチで）。

    ecobuild.toml の format（仕様の版）を今の版にし、ECOBuild が作ったファイルを今の中身にします：.gitignore・.gitattributes（足りない行を足す）、AGENTS.md・
    CIのワークフロー（あれば作り直す。手で編集したワークフローはそのまま）、型の生成ファイル。README は変えません。
    コミットはしないので、変わったファイルを確かめて ecobuild task commit してください。
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
            "確かめて ecobuild task commit --message \"ECOBuild の仕様に合わせる\" でコミットしてください" if r.paths else None,
        )

    return run_command("module upgrade", lambda inv: inv.module.upgrade(dry_run=dry_run), render, json_output=json)
