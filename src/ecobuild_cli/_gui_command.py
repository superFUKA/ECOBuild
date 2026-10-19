"""--gui（TortoiseGit）の共通処理。"""

from __future__ import annotations

from . import _gui
from ._output import Invocation, execute


def open_window(command: str, paths: tuple[str, ...], json_output: bool) -> int:
    def action(inv):
        target = (inv.cwd / paths[0]).resolve() if paths else inv.module.root
        _gui.open_window(command, target)
        return {"opened": command, "path": str(target)}

    return execute(command, Invocation(json_output=json_output), action, lambda r: f"TortoiseGitで開きました：{r['path']}")


def compare(name: str, revisions, json_output: bool) -> int:
    """2つのコミットの間の変更を TortoiseGit で開く（変更したファイルの一覧。ファイルを開くと差分）。
    revisions：inv → (前のコミット, 後のコミット)。同じなら開かない（opened は None：差分がない）。"""
    def action(inv):
        before, after = revisions(inv)
        if before == after:
            return {"opened": None, "path": str(inv.module.root), "revisions": [before, after]}
        _gui.open_window("showcompare", inv.module.root, revision1=before, revision2=after)
        return {"opened": "showcompare", "path": str(inv.module.root), "revisions": [before, after]}

    return execute(name, Invocation(json_output=json_output), action,
                   lambda r: f"TortoiseGitで開きました：{r['revisions'][0][:8]}..{r['revisions'][1][:8]}" if r["opened"]
                   else "差分はありません")
