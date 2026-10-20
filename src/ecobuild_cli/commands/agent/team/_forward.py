"""コンテナの中・GUI のエージェントの窓の中では、チームの操作をこのPCの係に頼む（ecobuild_agent.team.forward）。
係が持つアプリ用のエージェントの操作（引き取る・返す・アプリ用で起動する）は、このPCの端末からでも係に頼む（serve）。"""
import os
from pathlib import Path

import ecobuild_container as container
from ecobuild.errors import EcoBuildError
from ecobuild_agent.errors import ErrorCode
from ecobuild_agent import status as _status
from ecobuild_agent import team as _team

from ...._output import to_data


def run(inv, args: list[str], direct):
    """係に頼むときは args（ecobuild に渡すもの。--json は足す）を頼んで結果を返し、そうでなければ direct(inv)。
    結果はどちらも JSON にできる形（dict）。"""
    if not _team.should_forward():
        return to_data(direct(inv))
    return serve(inv, args)


def serve(inv, args: list[str]) -> dict:
    """いつも係に頼む（args の --json は足す）。このPCの端末からなら、係がこの作業空間の頼みを拾えるようにする。"""
    root = inv.module.root
    if not os.environ.get(container.INSIDE):
        _status.register(container.name(root), root)
    doc = _team.forward(root, [*args, "--json"], inv.cwd, progress=inv.info)
    if not doc.get("ok"):
        error = doc.get("error") or {}
        raise EcoBuildError(error.get("code") or ErrorCode.AGENT_ERROR, error.get("message") or "係での実行に失敗しました。",
                            hint=error.get("hint"), details=error.get("details"))
    return doc.get("result") or {}


def place(member: dict) -> str:
    """作業役の場所（進行役の作業空間からの場所。コンテナの中でも同じに読める）。"""
    return f"{_team.TEAM_AREA}/{Path(str(member.get('path', ''))).name}"
