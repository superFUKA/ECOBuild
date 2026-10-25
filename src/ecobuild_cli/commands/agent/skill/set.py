from typing import Annotated

import click
from click.core import ParameterSource
from ecobuild_agent import skills as _skills
from ecobuild_agent.results import skill_view

from ...._output import run_command
from .. import _change
from ..registry.set import _read_document
from . import _render
from .list import used_by


def command(name: Annotated[str, "スキルの名前"],
            description: Annotated[str, "説明（何をするか・いつ使うか）"] = "",
            document: Annotated[str, "本文のファイル（- なら標準入力）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュールのスキルの説明・本文を変え、タスクブランチでコミットします（書いたオプションだけを変えます）。

    SKILL.md のほかのファイル（スクリプト・資料）と、前置きのほかの行（allowed-tools 等）はそのままです。
    """
    def action(inv):
        new_description, text = changes(description, document)
        changed, sha = _change.in_task_branch(inv, f"スキル「{name}」を変える", lambda module: _skills.update(
            module.root, name, description=new_description, document=text))
        return skill_view(changed, document=True, pending=True, used_by=used_by(inv.module.root, name), committed=sha)

    return run_command("agent skill set", action, lambda r: "変えました：\n" + _render.details(r), json_output=json)


def changes(description: str, document: str) -> tuple[str | None, str | None]:
    """書いたオプションだけの (説明, 本文)（書いていなければ None。agent skill preset set も使う）。"""
    context = click.get_current_context()

    def given(option):
        return context.get_parameter_source(option) not in (ParameterSource.DEFAULT, ParameterSource.DEFAULT_MAP)

    return (description if given("description") else None,
            _read_document(document) if given("document") else None)
