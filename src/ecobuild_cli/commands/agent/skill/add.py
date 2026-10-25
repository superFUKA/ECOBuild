from typing import Annotated

from ecobuild_agent import skills as _skills
from ecobuild_agent.results import skill_view

from ...._output import run_command
from .. import _change
from ..registry.set import _read_document
from . import _render
from .list import used_by


def command(name: Annotated[str, "スキルの名前（英小文字・数字・-）"],
            description: Annotated[str, "説明（何をするか・いつ使うか。エージェントはこれを見て使うかを決める）"] = "",
            document: Annotated[str, "本文のファイル（- なら標準入力）"] = "",
            from_preset: Annotated[str, "写すこのPCのスキルの名前（agent skill preset list）"] = "",
            from_dir: Annotated[str, "取り込むフォルダー（SKILL.md がある。~/.claude/skills/<名前> 等）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュールにスキルを足し、タスクブランチでコミットします。

    置き場所は .ecobuild/agents/skills/<名前>/ です（SKILL.md と、それが使うファイル）。--from-preset でこのPCのスキルを
    写すか、--from-dir でフォルダーを取り込みます（ほかのファイルも一緒に）。どちらもなければ、--description と
    --document から作ります。中身は ecobuild agent skill set で変えます。

    例：
      ecobuild agent skill add release-notes --description "リリースノートを書くときの手順" --document notes.md
      ecobuild agent skill add pdf --from-dir ~/.claude/skills/pdf
    """
    def action(inv):
        text = _read_document(document) if document else None
        added, sha = _change.in_task_branch(inv, f"スキル「{name}」を足す", lambda module: _skills.add(
            module.root, name, description=description, document=text, from_preset=from_preset or None,
            from_dir=from_dir or None))
        return skill_view(added, document=True, pending=True, used_by=used_by(inv.module.root, name), committed=sha)

    return run_command("agent skill add", action, lambda r: "足しました：" + _render.details(r), json_output=json)
