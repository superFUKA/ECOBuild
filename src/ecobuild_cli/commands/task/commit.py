from typing import Annotated

from ..._output import lines, missing, run_command

AGENT = "owner"


def command(
    *paths: Annotated[str, "コミットするファイル・フォルダー（省略時：タスクブランチの変更すべて）"],
    message: Annotated[str, "コミットメッセージ（必須）"] = "",
    all: Annotated[bool, "（以前の書き方。指定しなくても変更はすべて含めます）"] = False,
    amend: Annotated[bool, "直前のコミットをやり直す"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクブランチの変更をコミットします（タスクブランチでのみ）。

    パスを省くと、変更・削除したファイルすべてと、管理するファイル（ecobuild track）に当たる新しいファイルを含めます。
    当たらない新しいファイルと、改行コード（CRLF／LF）だけが変わったファイルは含めず、一覧で知らせます。
    パスを書くと、そのファイルだけをコミットします（改行コードだけの変更も含めます）。
    """
    if not message and not amend:
        return missing("--message", json)

    def action(inv):
        module = inv.module
        relative = tuple(module.relative_path(p, inv.cwd) for p in paths)
        return module.commit(message, relative, amend=amend)

    def render(r):
        return lines(
            "\n".join(f"  {p}" for p in r.files) or None,
            f"管理するファイルの対象外ですが、指定どおり含めました：{', '.join(r.outside)}" if r.outside else None,
            f"含めなかった新しいファイル：{', '.join(r.skipped)}（管理するファイルの対象外。"
            "含めるなら ecobuild track add \"<パターン>\"、今回だけなら ecobuild task commit <パス> --message …）"
            if r.skipped else None,
            f"注意：改行コード（CRLF／LF）だけが変わったファイルは含めませんでした：{', '.join(r.eol_only)}"
            "（含めるなら ecobuild task commit <パス> --message …）" if r.eol_only else None,
            f"コミットしました：{r.sha[:8]} {r.message}（{len(r.files)} ファイル）",
        )

    return run_command("task commit", action, render, json_output=json)
