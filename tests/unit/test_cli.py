import click
from click.testing import CliRunner

from ecobuild_cli import build_cli


def test_help():
    result = CliRunner().invoke(build_cli(), ["--help"])
    assert result.exit_code == 0
    assert "ecobuild" in result.output


def test_short_help_is_not_cut():
    """一覧に出る説明（最初の段落）が長いと、Click が空白の位置で切って「...」にする（日本語では丸ごと消える）。
    最初の段落は短い1文にし、続きは次の段落に書く。"""
    cut = []

    def walk(group, path):
        ctx = click.Context(group, info_name=path)
        names = group.list_commands(ctx)
        limit = 78 - 6 - max(len(n) for n in names)   # 幅80の端末での一覧（Click の既定）
        for name in names:
            command = group.get_command(ctx, name)
            if command.get_short_help_str(limit).endswith("..."):
                cut.append(f"{path} {name}")
            if isinstance(command, click.Group):
                walk(command, f"{path} {name}")

    walk(build_cli(), "ecobuild")
    assert cut == []
