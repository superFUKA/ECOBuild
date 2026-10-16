"""CLI が使う Module：本体＋同梱の拡張（ecobuild_bundle）に、ヒントに書くプログラム名（ecobuild）を結び付ける。"""

import ecobuild_bundle

PROGRAM = "ecobuild"


class Module(ecobuild_bundle.Module):
    command = PROGRAM
