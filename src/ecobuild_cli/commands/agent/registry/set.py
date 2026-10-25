import sys
from pathlib import Path
from typing import Annotated

import click
from click.core import ParameterSource
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command, split_list
from .. import _change
from . import _render


def command(name: Annotated[str, "登録の名前"],
            title: Annotated[str, "表示名"] = "",
            human_start: Annotated[bool, "人が起動できる（--no-human-start で起動できない）"] = False,
            model: Annotated[str, "モデル（空なら Claude Code の既定）"] = "",
            tools: Annotated[str, "渡すツールの名前の並び（カンマ区切り。* 等の fnmatch。空なら何も渡さない）"] = "",
            children: Annotated[str, "起動してよい子の登録の名前（カンマ区切り。空なら子を起動しない）"] = "",
            skills: Annotated[str, "使えるスキルの名前の並び（カンマ区切り。* 等の fnmatch。空なら使わせない）"] = "",
            max_children: Annotated[int, "同時に持てる子の数の上限"] = 0,
            first_prompt: Annotated[str, "起動のときの最初の発言"] = "",
            evaluation: Annotated[str, "改善のループの評価のしかた（例：check（only=build,test）。空なら任された仕事に書かれたもの）"] = "",
            max_rounds: Annotated[int, "評価し直す回数の上限（0 なら決めない）"] = 0,
            max_turns: Annotated[int, "ターン数の上限（AI が起動したときに守らせる。0 ならなし）"] = 0,
            max_cost: Annotated[float, "費用の上限（ドル。AI が起動したときに守らせる。0 ならなし）"] = 0.0,
            lessons: Annotated[str, "教訓の記録先（モジュールの中のフォルダー。空なら報告だけ）"] = "",
            document: Annotated[str, "文書（agent.md）を読むファイル（- なら標準入力）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュールの登録の設定・文書を変え、タスクブランチでコミットします（書いたオプションだけを変えます）。

    見本の名前なら、モジュールの登録として写してから変えます（見本そのものは変わりません。元に戻すには
    ecobuild agent registry remove）。子に自分より強い登録（許すツールが多いもの）は入れられません。
    """
    def action(inv):
        fields, text = changes(title=title, human_start=human_start, model=model, tools=tools, skills=skills, children=children,
                               max_children=max_children, first_prompt=first_prompt, evaluation=evaluation,
                               max_rounds=max_rounds, max_turns=max_turns, max_cost=max_cost, lessons=lessons,
                               document=document)
        changed, sha = _change.in_task_branch(inv, f"エージェントの登録「{name}」を変える",
                                              lambda module: _registry.update(module.root, name, document=text, **fields))
        return registration_view(changed, document=True, pending=True, committed=sha)

    return run_command("agent registry set", action, lambda r: "変えました：\n" + _render.details(r), json_output=json)


def changes(**values) -> tuple[dict, str | None]:
    """書いたオプションだけの (設定の項目, 文書〔書いていなければ None〕)。何もなければ誤り（agent preset set も使う）。"""
    context = click.get_current_context()

    def given(option):
        return context.get_parameter_source(option) not in (ParameterSource.DEFAULT, ParameterSource.DEFAULT_MAP)

    converters = {"model": str.strip, "tools": split_list, "skills": split_list, "children": split_list, "evaluation": str.strip,
                  "lessons": str.strip}
    fields = {key: converters.get(key, lambda v: v)(value) for key, value in values.items()
              if key != "document" and given(key)}
    text = _read_document(values["document"]) if given("document") else None
    if not fields and text is None:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "変える項目がありません。",
                            hint="--model・--tools・--children・--document 等を書いてください。")
    return fields, text


def _read_document(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    try:
        return Path(source).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"文書のファイル {source} を読めません。",
                            details=str(error)) from error
