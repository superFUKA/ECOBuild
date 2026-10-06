from typing import Annotated

from .._output import run_command


def command(
    project: Annotated[str, "実行するProject（既定：実行ファイルのProjectの中ならそれ、それ以外は唯一の実行ファイル）"] = "",
    configuration: Annotated[str, "構成（Debug／Release等。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    arguments: Annotated[str, "プログラムへ渡す引数（1つの文字列）"] = "",
    json: Annotated[bool, "結果をJSONで出力する（プログラムの出力はresult.outputに入る）"] = False,
) -> int:
    """実行ファイルのProjectを実行します。"""

    def action(inv):
        module = inv.module
        target = project or module.executable_at(inv.cwd)
        return module.run(project=target, configuration=configuration, profile=profile or None, arguments=arguments)

    return run_command("run", action, lambda r: r.output, json_output=json)
