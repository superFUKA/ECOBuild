import sys
from dataclasses import dataclass
from importlib import metadata
from typing import Annotated

import ecobuild_bundle
from ecobuild.config import FORMAT
from ecobuild.errors import EcoBuildError
from ... import _gui, _self_update
from ..._module import PROGRAM
from ..._output import Invocation, execute, lines


@dataclass(frozen=True)
class InstallerInfo:
    version: str
    source: str              # 入れ元（git のURL・手元のソース。分からなければ空）
    ref: str | None
    commit: str | None
    editable: bool
    module_format: int       # この ECOBuild のモジュールの仕様の版（module upgrade）
    gui: str | None          # GUI の置き場所（入っていなければ None）
    python: str
    types: tuple[str, ...]   # 使えるモジュールの型
    tools: tuple             # ツール・機能（doctor の項目）


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """入っている ECOBuild（版・入れ元・GUI）と、使えるモジュールの型・ツールを表示します（何も変えません）。"""

    def action(inv):
        try:
            installed = _self_update.installed()
        except EcoBuildError:
            installed = _self_update.Installed("", None, None)
        gui = _self_update.GUI_DIRECTORY / "app.py"
        return InstallerInfo(
            metadata.version("ecobuild"), installed.url, installed.ref, installed.commit, installed.editable, FORMAT,
            str(gui.parent) if gui.is_file() else None, sys.version.split()[0],
            tuple(t.name for t in ecobuild_bundle.REGISTRY.available()),
            ecobuild_bundle.doctor(_gui.doctor_items(), command=PROGRAM).items)

    def render(r):
        source = ("開発用（手元のソース：" + r.source + "）" if r.editable else
                  f"{r.source}（{r.ref or '版の指定なし'}、{(r.commit or '不明')[:7]}）" if r.source else "不明")
        return lines(
            f"ECOBuild {r.version}：{source}",
            f"モジュールの仕様の版：{r.module_format}",
            f"GUI：{r.gui}" if r.gui else "GUI：入っていません（インストーラーで入れられます）",
            f"Python：{r.python}",
            f"モジュールの型：{'・'.join(r.types)}",
            "ツール・機能：\n" + "\n".join(("  OK " if i.ok else "  NG " if i.required else "  -- ") + f"{i.name}：{i.detail}"
                                       for i in r.tools),
            "更新は ecobuild installer update、あとから入れるのは ecobuild installer add（docker・tools）",
        )

    return execute("installer show", Invocation(json_output=json), action, render)
