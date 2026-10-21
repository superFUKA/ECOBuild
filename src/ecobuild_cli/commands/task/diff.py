from fnmatch import fnmatch
from typing import Annotated

from ..._gui_command import compare
from ..._output import optional_argument, run_command, split_list, usage_error

KINDS = {"A": "追加", "M": "変更", "D": "削除", "T": "種類の変更"}


def file_line(f) -> str:
    counts = "バイナリ" if f.added is None else f"+{f.added} -{f.deleted}"
    return f"  {KINDS.get(f.status, f.status)} {f.path}  {counts}" + ("（改行コードだけ）" if f.eol_only else "")


def command(
    *number: Annotated[int, "タスクの番号（--task と同じ）"],
    task: Annotated[int, "タスクの番号（既定は今いるタスクブランチ）"] = 0,
    stat: Annotated[bool, "変わったファイルごとの行数だけを表示する（JSON は files）"] = False,
    name_only: Annotated[bool, "変わったファイルの名前だけを表示する（JSON は files）"] = False,
    outside: Annotated[str, "このパターン（カンマ区切り。* は / も含む。例：src/ecowork/*）に当たらないファイルだけ"
                            "（持ち場の外の変更を確かめる。--name-only と同じ形）"] = "",
    gui: Annotated[bool, "TortoiseGitで表示する（Windows）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクの提出の差分を表示します（提出がなければ、タスクブランチの作成元との差分）。

    --stat・--name-only・--outside では、ファイルの一覧（JSON は files：path・status・added・deleted・eol_only）を出します。
    """
    task = optional_argument(number, task, "--task", json)
    patterns = split_list(outside)
    if gui and (stat or name_only or patterns):
        return usage_error("--gui は --stat・--name-only・--outside と一緒に使えません。", json)
    if gui:
        return compare("task diff", lambda inv: inv.module.repository.task_diff_revisions(task or None), json)
    if not (stat or name_only or patterns):
        return run_command("task diff", lambda inv: inv.module.repository.task_diff(task or None),
                           lambda r: r or "差分はありません", json_output=json)

    def files(inv):
        found = inv.module.repository.task_diff_files(task or None)
        return {"files": [f for f in found if not any(fnmatch(f.path, p) for p in patterns)]}

    def render(r):
        if not r["files"]:
            return "当たらないファイルの変更はありません" if patterns else "差分はありません"
        if stat:
            counted = [f for f in r["files"] if f.added is not None]
            return "\n".join([*map(file_line, r["files"]),
                              f"{len(r['files'])} ファイル（+{sum(f.added for f in counted)} "
                              f"-{sum(f.deleted for f in counted)}）"])
        return "\n".join(f.path for f in r["files"])

    return run_command("task diff", files, render, json_output=json)
