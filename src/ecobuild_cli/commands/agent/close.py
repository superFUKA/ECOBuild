from typing import Annotated

from ecobuild_agent import agents as _agents
from ecobuild_agent import children as _children

from ..._output import lines, run_command


def command(id: Annotated[str, "閉じるエージェントの ID（a- で始まる）"],
            force: Annotated[bool, "作業中・届いていない言付け・提出の後のコミットがあっても閉じる（子がいるときは閉じません）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """エージェントを閉じます（止めて、記録を消します）。

    エージェントが起動した子タスクの子なら、その作業空間も場所ごと消します（GitHub にない変更があれば閉じません）。
    報告・任された仕事は、親の作業空間の .ecobuild/ai/children-archive/<ID>-<名前>/ へ写します。子がいるエージェントは、
    先に子を閉じてから閉じます。作業中・届いていない言付け・提出の後のコミットがあるときも止めます（--force で閉じる）。
    """
    def action(inv):
        record = _agents.load(id)
        return _children.ask_serve(record, ["agent", "close", record.id, *(["--force"] if force else [])], inv.info)

    return run_command("agent close", action, _render, json_output=json)


def _render(r) -> str:
    return lines(f"「{r.get('name')}」（{r.get('id')}）を閉じました。",
                 "作業空間も閉じました。" if r.get("workspace") else None,
                 f"写したもの：{'、'.join(r['archive'])}" if r.get("archive") else None)
