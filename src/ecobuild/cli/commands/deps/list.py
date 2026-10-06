from typing import Annotated

from ..._output import run_command

STATES = {"aligned": "記録の版", "differs": "記録と別の版", "modified": "未コミットの変更あり",
          "working": "作業版", "missing": "cloneなし（ecobuild deps sync で取得）"}


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """依存先の一覧（記録の版・手元の版・状態）を表示します。"""

    def render(r):
        if not r:
            return "依存先はありません（ecobuild link で追加できます）"
        return "\n".join(
            f"{d.name}：記録 {d.recorded[:7]}、手元 {(d.local or '-')[:7]}、{STATES[d.state]}"
            + (f"（{d.branch}）" if d.branch else "") + f"\n  {d.url}" for d in r)

    return run_command("deps list", lambda inv: list(inv.module.dependencies()), render, json_output=json)
