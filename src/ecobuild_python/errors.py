"""型 python のエラーの種類（本体の ErrorCode に足す。値の文字は CLI・GUI が見るので変えない）。"""

from __future__ import annotations

from ecobuild.errors import ErrorCode as _ErrorCode


class ErrorCode(_ErrorCode):
    CLEAN_FAILED = "clean_failed"       # ビルドの成果物（dist/・build/ 等）を消せない
    RUN_INTERRUPTED = "run_interrupted"   # ecobuild run を止めた（SIGINT・SIGTERM）。プログラムも止めた
