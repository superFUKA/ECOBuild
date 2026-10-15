"""管理するファイル（新しいファイルのうち、task commit が自動でコミットに含めるもの）を扱います。"""

from typing import Annotated

from ..._output import lines, run_command

SOURCES = {"ecobuild": "ECOBuild", "type": "型の既定", "module": "このモジュール"}


def render(r) -> str:
    rows = [f"  {p.pattern}  （{SOURCES.get(p.source, p.source)}" + ("。外しています" if p.excluded else "") + "）"
            for p in r.patterns]
    return lines(
        "管理するファイル（新しいファイルのうち、ecobuild task commit が自動で含めるもの）：",
        "\n".join(rows),
        f"  {r.managed_note}・ECOBuildのコマンドで作ったファイルも含めます" if r.managed_note
        else "  ECOBuildのコマンドで作ったファイルも含めます",
        f"外しているもの：{', '.join(r.exclude)}" if r.exclude else None,
        "変えるには ecobuild track add／remove \"<パターン>\"（ecobuild.toml の [files]。作業空間でコミット）",
    )


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """管理するファイルのパターンを、出どころ（ECOBuild・型の既定・このモジュール）とともに表示します。

    パターンは .gitignore と同じ書き方です（/ を含まなければどの階層の名前にも当たる。例："*.txt"・"data/**"）。
    """
    return run_command("track", lambda inv: inv.module.tracked_files(), render, json_output=json)
