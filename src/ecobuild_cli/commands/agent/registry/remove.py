from typing import Annotated

from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command
from .. import _change


def command(name: Annotated[str, "登録の名前"],
            yes: Annotated[bool, "確認せずに実行する"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュールの登録を消し、タスクブランチでコミットします（文書ごと。同じ名前の見本があれば、また見本が使われます）。

    見本は消せません。
    """
    def action(inv):
        current = _registry.load(name, inv.module.root)
        if current.source != _registry.MODULE:
            _registry.remove(inv.module.root, name)      # 見本は消せない：確認の前に知らせる
        inv.confirm(f"登録「{name}」を文書ごと消しますか？")
        removed, sha = _change.in_task_branch(inv, f"エージェントの登録「{name}」を消す",
                                              lambda module: _registry.remove(module.root, name))
        return registration_view(removed, document=True, committed=sha)

    return run_command("agent registry remove", action, lambda r: f"登録「{r.name}」を消しました",
                       json_output=json, yes=yes)
