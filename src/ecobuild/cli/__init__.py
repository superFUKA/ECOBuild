"""ECOBuildのCLI。コマンドの定義はcommandsパッケージに置き、CLIFrameWorkで組み立てる。"""

from cli_framework import create_cli

from . import commands
from ._output import use_utf8_when_redirected


def build_cli():
    return create_cli(commands, name="ecobuild")


def main() -> None:
    use_utf8_when_redirected()
    build_cli()()
