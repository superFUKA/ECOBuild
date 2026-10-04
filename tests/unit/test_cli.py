from click.testing import CliRunner

from ecobuild.cli import build_cli


def test_help():
    result = CliRunner().invoke(build_cli(), ["--help"])
    assert result.exit_code == 0
    assert "ecobuild" in result.output
