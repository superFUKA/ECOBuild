"""ファイル操作の小さな共通処理（本体と型の両方で使う）。"""

from __future__ import annotations

import os
import shutil
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def remove_tree(path: Path) -> None:
    """gitの読み取り専用ファイル（Windows）も含めて削除する。"""
    def retry(function, target, _):
        os.chmod(target, stat.S_IWRITE)
        function(target)
    shutil.rmtree(path, onerror=retry)


@contextmanager
def locked(path: Path, *, timeout: float = 30.0, wait: bool = True) -> Iterator[None]:
    """ファイル path の排他ロックを持つ間だけ、中を実行する（このPCのほかのプロセス・スレッドと1つずつにする。
    プロセスが終われば OS が外す）。wait=False なら待たず、持てなければすぐ BlockingIOError。timeout 秒待っても
    持てなければ TimeoutError（どちらも OSError：失敗しても止めない処理は OSError で受ける）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    until = time.monotonic() + timeout
    with open(path, "a+") as file:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    file.seek(0)
                    msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if not wait:
                    raise BlockingIOError(f"{path} は使用中です。") from None
                if time.monotonic() >= until:
                    raise TimeoutError(f"{path} のロックを待ちきれませんでした。") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)


def process_alive(pid: int) -> bool:
    """このPCのプロセス pid が動いているか。"""
    if pid <= 0:
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
