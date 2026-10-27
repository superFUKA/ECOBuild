from typing import Annotated

from ecobuild.errors import WorkError
from ecobuild_agent import inside as _inside

from ...._module import PROGRAM
from ...._output import Invocation, execute, lines


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """コンテナの中の Claude Code の版を表示します（設定の版と、今の作業空間の動いているコンテナの中の版）。

    設定は agent_claude_version（例 2.1.302・stable・latest。空ならイメージを作るときの最新）。変えると、次にコンテナを
    動かすときにイメージを作り直します。中の版は、今の作業空間のコンテナが動いているときだけ読みます。
    """
    def action(inv):
        try:
            root = inv.module.root
        except WorkError:
            root = None   # モジュールの外：設定の版だけ
        installed, reason = _inside.installed_version(root) if root is not None else ("", "")
        return {"setting": _inside.claude_version(), "key": _inside.VERSION_KEY, "installed": installed or None,
                "reason": reason or None}

    return execute("agent version status", Invocation(json_output=json), action, _render)


def _render(r) -> str:
    setting = r["setting"] or "指定なし（イメージを作るときの最新）"
    return lines(f"設定の版：{setting}（{PROGRAM} config set {r['key']} <版>）",
                 f"コンテナの中の版：{r['installed']}" if r["installed"] else r["reason"])
