import sys
from pathlib import Path
from typing import Annotated

import click
from click.core import ParameterSource
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command, split_list
from . import _render


def command(name: Annotated[str, "登録の名前"],
            title: Annotated[str, "表示名"] = "",
            human_start: Annotated[bool, "人が起動できる（--no-human-start で起動できない）"] = False,
            model: Annotated[str, "モデル（空なら Claude Code の既定）"] = "",
            tools: Annotated[str, "渡すツールの名前の並び（カンマ区切り。* 等の fnmatch。空なら何も渡さない）"] = "",
            children: Annotated[str, "起動してよい子の登録の名前（カンマ区切り。空なら子を起動しない）"] = "",
            max_children: Annotated[int, "同時に持てる子の数の上限"] = 0,
            first_prompt: Annotated[str, "起動のときの最初の発言"] = "",
            document: Annotated[str, "文書（agent.md）を読むファイル（- なら標準入力）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """登録の設定・文書を変えます（書いたオプションだけを変えます）。

    見本の名前なら、ユーザーの登録として写してから変えます（見本そのものは変わりません。元に戻すには
    ecobuild agent registry remove）。子に自分より強い登録（許すツールが多いもの）は入れられません。
    """
    context = click.get_current_context()

    def given(option):
        return context.get_parameter_source(option) not in (ParameterSource.DEFAULT, ParameterSource.DEFAULT_MAP)

    def action(inv):
        fields = {key: value for key, value in (
            ("title", title), ("human_start", human_start), ("model", model.strip()),
            ("tools", split_list(tools)), ("children", split_list(children)), ("max_children", max_children),
            ("first_prompt", first_prompt)) if given(key)}
        text = None
        if given("document"):
            text = _read_document(document)
        if not fields and text is None:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "変える項目がありません。",
                                hint="--model・--tools・--children・--document 等を書いてください。")
        return registration_view(_registry.update(name, document=text, **fields), document=True)

    return run_command("agent registry set", action, lambda r: "変えました：\n" + _render.details(r),
                       json_output=json)


def _read_document(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    try:
        return Path(source).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"文書のファイル {source} を読めません。",
                            details=str(error)) from error
