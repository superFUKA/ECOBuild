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
    """gitの読み取り専用ファイル（Windows）も含めて削除する。

    読み取り専用を外して消し直すのは Windows だけ：POSIX では消せない理由が権限でない（マウント点・使用中等）ことが多く、
    chmod(S_IWRITE) すると権限が 0200 に変わったまま残る。消せなければ、そのときの誤り（OSError）を出す。
    """
    def retry(function, target, excinfo):
        if os.name != "nt":
            raise excinfo[1]
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


REUSE_SLACK = 2.0   # 起動の時刻の比べ方のゆとり（秒。記録はプロセスが起動した後に書く）


def process_alive(pid: int, since: float | None = None) -> bool:
    """このPCのプロセス pid が動いているか。since（そのプロセスが起動していたと分かっている時刻。記録を書いた時刻）
    があれば、pid が使い回されたもの（since より後に起動した別のプログラム。Windows は pid をすぐ使い回す）は
    動いていないとみなす。起動の時刻が分からなければ pid だけで決める。"""
    if pid <= 0:
        return False
    if since is not None:
        begun = process_started(pid)
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


def process_started(pid: int) -> float | None:
    """このPCのプロセス pid が起動した時刻（UNIX 時刻）。分からなければ（ない・権限がない・調べ方のない OS）None。"""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            times = [wintypes.FILETIME() for _ in range(4)]   # 起動・終了・カーネル・ユーザー
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                return None
            created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime   # 1601 年からの 100 ナノ秒
            return (created - 116444736000000000) / 10_000_000
        finally:
            kernel.CloseHandle(handle)
    try:   # Linux：/proc の起動からの時間（クロックの刻み）＋ 起動した時刻
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        boot = next(float(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines()
                    if line.startswith("btime "))
        return boot + int(fields[19]) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError, StopIteration, AttributeError):
        return None


def kill_tree(pid: int) -> None:
    """プロセス pid を、その子ごと止める。Windows では親を止めても子は残る（wsl.exe は中にもう1つ wsl.exe を、
    ecobuild.exe は python を起こす）ので、taskkill /T で木ごと。ほかの OS では pid だけ（子は親と一緒に止まる前提）。"""
    import signal
    import subprocess
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, stdin=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
