import signal
from typing import Annotated

from ecobuild.errors import EcoBuildError
from ecobuild_cli.kit import ProgramOutput, run_command, usage_error
from ecobuild_python import _python

AGENT = "change"


def command(
    *argv: Annotated[str, "プログラムへ渡す引数（-- の後ろに並べる：ecobuild run -- --port 8080 \"a b\"）"],
    configuration: Annotated[str, "構成（Debug／Release。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    arguments: Annotated[str, "プログラムへ渡す引数（1つの文字列。shlex で分ける：空白で区切り、\"…\" でまとめる。"
                              "Windows では \\ はそのまま）。-- の後ろに並べるのと同じ"] = "",
    stdin: Annotated[bool, "--json でも標準入力をプログラムに渡す（--json なしでは、いつも渡す）"] = False,
    input_file: Annotated[str, "標準入力の代わりに、このファイルの中身をプログラムに渡す"] = "",
    propagate_exit: Annotated[bool, "ecobuild の終了コードを、プログラムの終了コードにする（止めたら 128＋シグナルの番号）"] = False,
    json: Annotated[bool, "結果をJSONで出力する（出力は result の stdout・stderr〔output は stdout〕、終了コードは"
                          "returncode。失敗・中断のときは error.details に同じ欄）"] = False,
) -> int:
    """pyproject.toml の [project.scripts] のコマンドを、venv で実行します。

    出力はためずにそのまま流し、標準入力も渡します（対話型・Web サーバー等）。--json では出力を分けてためて
    result に入れ、実行中は標準エラーにも流します（output のイベントで。stdout・stderr の別も）。Ctrl+C・SIGTERM で
    止めると、プログラムも止めます。
    """
    if arguments and argv:
        return usage_error("--arguments と -- の後ろの引数は、どちらか1つにしてください。", json)
    if stdin and input_file:
        return usage_error("--stdin と --input-file は、どちらか1つにしてください。", json)
    ran = {}

    def action(inv):
        module = inv.module
        options, _ = module.build_options(configuration, profile or None)
        values = list(argv) if argv else _python.split_arguments(arguments)
        source = str(inv.cwd / input_file) if input_file else "inherit" if stdin or not json else None
        try:
            result = module.type.run_program(options, values, stream=not json, stdin=source,
                                             echo=ProgramOutput(True) if json else False,
                                             on_start=lambda shown, pid: inv.info(f"実行中（PID {pid}）：{shown}"))
        except EcoBuildError as error:
            details = error.details if isinstance(error.details, dict) else {}
            if "signal" in details:
                ran["code"] = 128 + int(getattr(signal, details["signal"]))
            elif "returncode" in details:
                ran["code"] = _exit_code(details["returncode"])
            raise
        ran["code"] = result.returncode
        return result

    # 出力は流し終えている（--json では result に入る）ので、終わってから表示するものはない
    code = run_command("run", action, lambda r: None, json_output=json)
    return ran["code"] if propagate_exit and "code" in ran else code


def _exit_code(returncode: int) -> int:
    """プログラムの終了コード（シグナルで終わったとき〔負〕は 128＋番号。sh と同じ）。"""
    return 128 - returncode if returncode < 0 else returncode
