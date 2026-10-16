import re

import click
import pytest

from ecobuild import _docs
from ecobuild.config import ModuleConfig
from ecobuild_bundle import REGISTRY
from ecobuild_cli import build_cli

_MENTION = re.compile(r"`ecobuild((?: [a-z][a-z-]*)+)")


def _exists(cli: click.Group, words: list[str]) -> bool:
    """ecobuild のあとの語が、コマンドとしてたどれるか（たどり着いたコマンドのあとの語は引数とみなす）。"""
    context = click.Context(cli)
    command = cli
    for word in words:
        if not isinstance(command, click.Group):
            return True
        command = command.get_command(context, word)
        if command is None:
            return False
        context = click.Context(command, parent=context)
    return True


def _documents(name: str) -> dict[str, str]:
    module_type = REGISTRY.load(name)
    config = ModuleConfig(name="Sample", type=name)
    return {"AGENTS.md": _docs.agents(config, module_type), "agent guide": _docs.agent_guide(config, module_type)}


@pytest.mark.parametrize("name", sorted(REGISTRY.entries()))
def test_mentioned_commands_exist(name):
    """AGENTS.md と agent guide が案内するコマンドは、すべて実在する（古い案内を出さない）。"""
    cli = build_cli(name)        # 型ごとのコマンドは、その型のモジュールの中でだけ出る
    for document, text in _documents(name).items():
        missing = [m for m in _MENTION.findall(text) if not _exists(cli, m.split())]
        assert missing == [], f"{name} の {document}"


@pytest.mark.parametrize("name", sorted(REGISTRY.entries()))
def test_agents_md_points_to_the_guide(name):
    """AGENTS.md は核だけで、手順は agent guide に任せる（ECOBuild を変えても古くならない）。"""
    documents = _documents(name)
    assert "`ecobuild agent guide`" in documents["AGENTS.md"]
    assert "## 作業の流れ" not in documents["AGENTS.md"] and "## 作業の流れ" in documents["agent guide"]
    assert len(documents["AGENTS.md"].splitlines()) <= 12


def test_guide_follows_the_type():
    """ファイルの追加を受け持たない型には、file add を案内しない。"""
    assert "ecobuild file add" in _documents("cpp")["agent guide"]
    assert "ecobuild file add" not in _documents("generic")["agent guide"]
