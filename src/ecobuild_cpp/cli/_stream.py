"""build・clean・rebuild・test の共通部分（ツールの出力を実行中に流す）。"""

from contextlib import nullcontext

from ecobuild_cli.kit import ProgramOutput
from ecobuild_cpp import CppType


def tool_output(json_output: bool):
    """--json のとき、CMake・コンパイラー・テストの出力を実行中に標準エラーへ流す（行の頭に「│ 」。GUI の出力欄が、
    終わる前から見える）。人向けは今までどおり（終わってから結果。失敗したら誤りの詳細に出力）。with で使う。"""
    return CppType.program_output(ProgramOutput(True).line) if json_output else nullcontext()
