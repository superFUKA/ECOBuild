"""--gui（TortoiseGit）の共通処理。"""

from __future__ import annotations

from .. import _gui
from ._output import Invocation, execute


def open_window(command: str, paths: tuple[str, ...], json_output: bool) -> int:
    def action(inv):
        target = (inv.cwd / paths[0]).resolve() if paths else inv.module.root
        _gui.open_window(command, target)
        return {"opened": command, "path": str(target)}

    return execute(command, Invocation(json_output=json_output), action, lambda r: f"TortoiseGitで開きました：{r['path']}")
