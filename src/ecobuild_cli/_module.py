"""CLI が使う Module：本体＋同梱の拡張（ecobuild_bundle）に、ヒントに書くプログラム名（ecobuild）を結び付ける。"""

import shutil
import sys
from pathlib import Path

import ecobuild_bundle

PROGRAM = "ecobuild"


def program_path() -> str:
    """フック・別の窓で呼ぶ ecobuild（このコマンドを動かしているもの。見つからなければ PATH の名前）。"""
    here = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    for candidate in (here, here.with_suffix(".exe")) if here is not None and here.stem.lower() == PROGRAM else ():
        if candidate.is_file():
            return candidate.resolve().as_posix()
    found = shutil.which(PROGRAM)
    return Path(found).as_posix() if found else PROGRAM


class Module(ecobuild_bundle.Module):
    command = PROGRAM

    def container_source(self):
        """コンテナのイメージに入れる ECOBuild：このPCの ecobuild と同じ版。"""
        from .commands.container._source import source
        return source()
