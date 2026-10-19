from typing import Annotated

from ecobuild_cli.kit import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """構成（Visual Studio のソリューション等）を今のファイルに合わせます（ビルドはしません）。

    ecobuild file add・move・remove は自動で行います。コンテナの中やエディターでファイルを足した・移したとき、
    このPCの Visual Studio に反映するのに使います（コンテナの作業空間でも、このPCで行います）。
    """
    return run_command("project update", lambda inv: inv.module.type.update_solution(),
                       lambda r: "構成を作り直しました" if r["configured"] else "構成は最新です", json_output=json)
