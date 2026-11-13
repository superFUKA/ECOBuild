"""このPCのプロセスが生きているか（実行のロックの持ち主を確かめる）。"""

from __future__ import annotations

import os
from pathlib import Path

REUSE_SLACK = 2.0   # 起動の時刻の比べ方のゆとり（秒）


def alive(pid: int, since: float | None = None) -> bool:
    """プロセス pid が動いているか。since（ロックを書いた時刻）より後に起動したもの（pid の使い回し）は除く。"""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if since is not None:
        begun = started(pid)
        if begun is not None and begun > since + REUSE_SLACK:
            return False
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def started(pid: int) -> float | None:
    """プロセス pid が起動した時刻（UNIX 時刻。分からなければ None）。"""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                return None
            created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            return (created - 116444736000000000) / 10_000_000
        finally:
            kernel.CloseHandle(handle)
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        boot = next(float(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines()
                    if line.startswith("btime "))
        return boot + int(fields[19]) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError, StopIteration, AttributeError):
        return None
