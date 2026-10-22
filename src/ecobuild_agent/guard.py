"""シェルのコマンドの関所（ecobuild agent guard）：許すのは ecobuild と読むだけのコマンド。重さは使う側（CLI）が決める。

オペレーターが GUI の側（gui/operator_kit.py。シェルを使わない）へ移ったので、今これを使うエージェントはない。
作業空間のエージェントの関所（ダメなものの列挙）に作り直すまでの、前からの形。
"""

from __future__ import annotations

from typing import Callable

import ecoagent

HUMAN = ecoagent.guard.HUMAN


def hook(data: str, classify: Callable[[list[str]], tuple[str, str]], *, program: str) -> tuple[int, str]:
    """シェルのコマンド（フックの入力の JSON）を調べる。(終了コード, エージェントに伝える文)。
    classify：program の引数 → (重さ, コマンドの名前)。"""
    policy = ecoagent.guard.Policy(
        frozenset({program}), classify, role="エージェント",
        refusals={HUMAN: f"これは人が行う操作です（{program} の準備・更新・秘密の値の入力など）。"
                         "ユーザーに、自分で実行するよう伝えてください。"})
    return ecoagent.guard.hook(data, policy)
