from typing import Annotated

from ecobuild_agent import skills as _skills
from ecobuild_agent.results import skill_view

from ....._output import run_command
from ...registry.set import _read_document
from .. import _render


def command(name: Annotated[str, "スキルの名前（英小文字・数字・-）"],
            description: Annotated[str, "説明（何をするか・いつ使うか）"] = "",
            document: Annotated[str, "本文のファイル（- なら標準入力）"] = "",
            from_module: Annotated[str, "写す、今いるモジュールのスキルの名前（作業空間のもの）"] = "",
            from_dir: Annotated[str, "取り込むフォルダー（SKILL.md がある。~/.claude/skills/<名前> 等）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """このPCにスキルを足します（ECOBUILD_HOME/agents/skills/<名前>/。コミットしません）。

    --from-module で今いるモジュールのスキルを写すか、--from-dir でフォルダーを取り込みます（ほかのファイルも一緒に）。
    どちらもなければ、--description と --document から作ります。

    例：
      ecobuild agent skill preset add pdf --from-dir ~/.claude/skills/pdf
      ecobuild -C C:\\ECO\\Calc agent skill preset add release-notes --from-module release-notes
    """
    def action(inv):
        text = _read_document(document) if document else None
        source = (inv.module.root, from_module) if from_module else None
        return skill_view(_skills.add_preset(name, description=description, document=text, from_dir=from_dir or None,
                                             from_module=source), document=True)

    return run_command("agent skill preset add", action, lambda r: "このPCのスキルにしました：" + _render.summary(r),
                       json_output=json)
