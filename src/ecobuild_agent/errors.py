"""エージェントの拡張のエラーの種類（本体の ErrorCode に足す。値の文字は CLI・GUI が見るので変えない）。"""

from __future__ import annotations

from ecobuild.errors import ErrorCode as _ErrorCode


class ErrorCode(_ErrorCode):
    AGENT_ERROR = "agent_error"         # エージェントを起動できない（details に ecoagent の code）


def from_ecoagent(error):
    """ecoagent のエラーを、ECOBuild のエラーにする。"""
    from ecobuild.errors import EcoBuildError
    return EcoBuildError(ErrorCode.AGENT_ERROR, error.message, hint=error.hint, details=error.code)
