from typing import Annotated

from ..._output import run_command, usage_error
from ._common import flows, render_run


def command(name: Annotated[str, "流れの名前（.ecobuild/flows/<名前>.toml）"],
            *values: Annotated[str, "入力（<名前>=<値>。いくつでも）"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """流れを実行します。人の答え待ち（approval）か、終わり・失敗まで進めて戻ります（それまで待ちます。進み具合は標準エラー）。

    実行は作業空間の .ecobuild/flows/runs/<実行>/ に残ります。人の答え待ちなら ecobuild flow approve／reject、失敗なら
    ecobuild flow retry、途中で止めた（Ctrl+C 等）なら ecobuild flow resume で続けます。工程が失敗して止まっても
    終了コードは 0 です（結果の status で見ます）。

    例：
      ecobuild flow run fix-until-green goal="0除算で落ちる"
    """
    inputs = {}
    for value in values:
        key, sep, text = value.partition("=")
        if not sep or not key.strip():
            return usage_error(f"入力「{value}」は <名前>=<値> で書きます。", json)
        inputs[key.strip()] = text
    return run_command("flow run", lambda inv: flows(inv).run(name, inputs), render_run, json_output=json)
