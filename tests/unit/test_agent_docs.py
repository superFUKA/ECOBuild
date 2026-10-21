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
    """ファイルの追加を受け持つ型には、file add を案内する（generic も空のファイルを作る）。"""
    assert "ecobuild file add" in _documents("cpp")["agent guide"]
    assert "ecobuild file add" in _documents("generic")["agent guide"]


@pytest.mark.parametrize("name", sorted(REGISTRY.entries()))
def test_guide_asks_for_ecobuild_first(name):
    """手でする前に、ECOBuild のコマンドでできるかを確かめる（なければ直接でよい）。"""
    guide = _documents(name)["agent guide"]
    assert "## まず ECOBuild でできるかを考える" in guide and "直接して構いません" in guide
    assert "`ecobuild build`・`ecobuild test`・`ecobuild run`" in guide and "直接使いません" in guide
    assert "ecobuild file add／move／remove" in guide


@pytest.mark.parametrize("name", sorted(REGISTRY.entries()))
def test_readme_is_modest(name):
    """README は題名・説明・型ごとの最低限の使い方だけで、ECOBuild のこと（名前・設定・コマンド）は書かない。"""
    readme = _docs.readme(ModuleConfig(name="Sample", type=name), REGISTRY.load(name), "サンプルの説明")
    assert readme.startswith("# Sample\n\nサンプルの説明\n")
    assert "ECOBuild" not in readme and "ecobuild.toml" not in readme and "`ecobuild " not in readme
    assert _docs.readme(ModuleConfig(name="Sample", type=name), REGISTRY.load(name)).startswith("# Sample\n")


@pytest.mark.parametrize("name", sorted(REGISTRY.entries()))
def test_ecobuild_readme_mentions_existing_commands(name):
    """.ecobuild/README.md（ECOBuild から見たこのモジュール）が案内するコマンドは実在する。"""
    text = _docs.ecobuild_readme(ModuleConfig(name="Sample", type=name), REGISTRY.load(name))
    assert text.startswith("# ECOBuild（Sample）\n") and f"型：{name}" in text
    missing = [m for m in _MENTION.findall(text) if not _exists(build_cli(name), m.split())]
    assert missing == []


def test_generic_commands_are_not_in_the_readme():
    """generic の [commands] の書き方は、ルートの README ではなく .ecobuild/README.md と agent guide に出る。"""
    config, generic = ModuleConfig(name="Sample", type="generic"), REGISTRY.load("generic")
    assert "[commands]" not in _docs.readme(config, generic)
    assert "[commands]" in _docs.ecobuild_readme(config, generic) and "[commands]" in _documents("generic")["agent guide"]
    assert "[commands]" not in _docs.ecobuild_readme(ModuleConfig(name="Sample", type="cpp"), REGISTRY.load("cpp"))
