"""ECOBuildのCLI。コマンドの定義はcommandsパッケージに置き、CLIFrameWorkで組み立てる。"""

from cli_framework import create_cli

from . import commands


def build_cli():
    return create_cli(commands, name="ecobuild")


def main() -> None:
    build_cli()()
