"""コンテナの中・GUI のエージェントの窓の中では、チームの操作をこのPCの係に頼む（ecobuild_bundle.team.forward）。"""
from pathlib import Path

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_bundle import team as _team

from ...._output import to_data


def run(inv, args: list[str], direct):
    """係に頼むときは args（ecobuild に渡すもの。--json は足す）を頼んで結果を返し、そうでなければ direct(inv)。
    結果はどちらも JSON にできる形（dict）。"""
    if not _team.should_forward():
        return to_data(direct(inv))
    doc = _team.forward(inv.module.root, [*args, "--json"], inv.cwd)
    if not doc.get("ok"):
        error = doc.get("error") or {}
        raise EcoBuildError(error.get("code") or ErrorCode.AGENT_ERROR, error.get("message") or "係での実行に失敗しました。",
                            hint=error.get("hint"), details=error.get("details"))
    return doc.get("result") or {}


def place(member: dict) -> str:
    """作業役の場所（進行役の作業空間からの場所。コンテナの中でも同じに読める）。"""
    return f"{_team.TEAM_AREA}/{Path(str(member.get('path', ''))).name}"
