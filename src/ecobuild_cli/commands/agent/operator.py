from typing import Annotated

from ecobuild_bundle import operator

from ... import build_cli
from ..._operator import prepare as prepare_kit
from ..._output import Invocation, execute


def command(agent: Annotated[str, "起動するエージェントのコマンド（引数は空白で区切る。既定は claude）"] = "",
            prepare: Annotated[bool, "起動せずに、一式（指示・許可・フック）を置いて場所を表示する（別のアプリから起動するとき）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """オペレーター（ECOBuild の操作係のエージェント）を新しい画面で起動します。

    オペレーターはコードを書かず、頼まれた ECOBuild の操作を ecobuild コマンドで行います。どこからでも起動できます
    （モジュールの中でなくてよい）。作業ディレクトリは ECOBUILD_HOME/agents/operator で、起動のたびに、今の ECOBuild の
    コマンドの一覧から指示（CLAUDE.md）と許可・フック（.claude/settings.json）を作り直します。
    消す・取り返しのつかない操作は、ユーザーに聞いて「はい」と答えたときだけ実行します（フックで止めます）。
    画面を開かずに話しかけるのは ecobuild agent ask です。
    """
    def action(inv):
        kit = prepare_kit(build_cli)
        if prepare:
            return kit
        return operator.start(tuple(agent.split())) if agent.strip() else operator.start()

    def render(r):
        if isinstance(r, operator.OperatorKit):
            return f"オペレーターの一式を置きました：{r.directory}（ここでエージェントを起動すると使えます）"
        return f"オペレーターを起動しました：{' '.join(r.command)}（{r.directory}）"

    return execute("agent operator", Invocation(json_output=json), action, render)
