from typing import Annotated

from ... import _self_update
from ..._output import lines, run_command


def command(
    check: Annotated[bool, "新しい版があるかを確かめるだけ（入れ直さない）"] = False,
    ref: Annotated[str, "入れる版（ブランチ・タグ・コミット）。省略時は入れたときの版（ブランチなら、その最新）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ECOBuild（CLI と GUI）を GitHub の最新に更新します。

    入れたときのインストーラーと同じ手順で入れ直します。Windows では別の窓で、この ecobuild が終わってから
    行います（動いている ecobuild・GUI は置き換えられないため。GUI は閉じます）。終わったら、開いているモジュールで
    ecobuild status を見ると、モジュールを今の仕様に合わせるか（module upgrade）が分かります。
    """

    def action(inv):
        return _self_update.check(ref or None) if check else _self_update.update(ref or None)

    def render(r):
        versions = f"{_short(r.current)} → {_short(r.latest)}（{r.ref}）"
        if r.up_to_date:
            return f"最新です：{_short(r.latest)}（{r.ref}）"
        if not r.started:
            return lines(f"新しい版があります：{versions}", "更新するには ecobuild installer update")
        return lines(f"更新を始めました：{versions}",
                     "別の窓でインストーラーが動きます。終わったら、新しい端末で ecobuild を使ってください。"
                     + ("（GUI も入れ直すので、開いていれば閉じます）" if r.gui else ""))

    return run_command("installer update", action, render, json_output=json)


def _short(commit):
    return commit[:7] if commit else "不明"
