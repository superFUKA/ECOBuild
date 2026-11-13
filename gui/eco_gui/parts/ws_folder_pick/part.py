"""移動先のフォルダーを選ぶ（選んだいくつものファイル・フォルダーを、1つのフォルダーへ移す。前の GUI の moveChosenDialog と同じ）。

動かすものの一覧と、移動先のフォルダーの欄。動かすフォルダーの中・「.」で始まるフォルダー・build は候補に出さない。サブプロジェクトの
ある型では、サブプロジェクトのフォルダーの中だけ（一番上には置けない）。決めたら move で出す（移すのは ecobuild file move … --into）。"""
from typing import Annotated


def part(
    paths: Annotated[list[str], "動かすファイル・フォルダー"] = [],
    files: Annotated[list[str], "今あるファイル（フォルダーの候補を作る）"] = [],
    folders: Annotated[list[str] | None, "中にファイルのないフォルダー（ecobuild files の folders。これも候補）"] = None,
    projects: Annotated[list | None, "サブプロジェクト（名前か {name, directory}）。あれば、そのフォルダーの中だけを候補にする"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_move(into: Annotated[str, "移動先のフォルダー（一番上なら「.」）"] = ".") -> None: ...


def on_cancel() -> None: ...
