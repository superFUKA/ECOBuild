from typing import Annotated

from ecobuild_cli.kit import ProgramOutput, optional_argument, run_like
from ecobuild_cpp import CppType

AGENT = "change"


def command(
    *projects: Annotated[str, "実行するProject（--project と同じ）"],
    project: Annotated[str, "実行するProject（既定：実行ファイルのProjectの中ならそれ、それ以外は唯一の実行ファイル）"] = "",
    configuration: Annotated[str, "構成（Debug／Release等。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    arguments: Annotated[str, "プログラムへ渡す引数（1つの文字列）"] = "",
    json: Annotated[bool, "結果をJSONで出力する（プログラムの出力はresult.outputに入る）"] = False,
) -> int:
    """実行ファイルのProjectを実行します。

    プログラムの出力は、実行中に流します（--json では標準エラーへ output のイベントで。その前のビルドの出力も）。
    """
    project = optional_argument(projects, project, "--project", json)
    # 人向けはプログラムの出力だけ（stdout は標準出力・stderr は標準エラーへ。ビルドの出力は、今までどおり失敗したときに
    # 誤りの詳細で）
    with CppType.program_output(ProgramOutput(json).line, tools=json):
        return run_like(project, configuration, profile, arguments, json, streamed=True)
