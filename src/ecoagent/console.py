"""今の端末の画面の文字を読む（Windows のコンソールだけ。ほかは空）。

別のプログラムを同じ画面で動かした後に、そのプログラムが画面に出したもの（ログインのトークン等）を拾うためのもの。
画面の幅いっぱいまで続く行は、次の行と続けて1行にする（長い文字列が折り返されても1つにつながる）。
"""

from __future__ import annotations

import sys


def screen_text() -> str:
    if sys.platform != "win32":
        return ""
    try:
        return _windows_screen()
    except (OSError, AttributeError, ValueError):
        return ""


def _windows_screen() -> str:
    import ctypes
    from ctypes import wintypes

    class COORD(ctypes.Structure):
        _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

    class SMALL_RECT(ctypes.Structure):
        _fields_ = [("Left", wintypes.SHORT), ("Top", wintypes.SHORT), ("Right", wintypes.SHORT), ("Bottom", wintypes.SHORT)]

    class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
        _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD), ("wAttributes", wintypes.WORD),
                    ("srWindow", SMALL_RECT), ("dwMaximumWindowSize", COORD)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel32.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(CONSOLE_SCREEN_BUFFER_INFO)]
    kernel32.ReadConsoleOutputCharacterW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, COORD,
                                                     ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.CreateFileW("CONOUT$", 0xC0000000, 3, None, 3, 0, None)   # 読み書き・共有・既存のもの
    if handle in (None, 0, ctypes.c_void_p(-1).value):
        return ""
    try:
        info = CONSOLE_SCREEN_BUFFER_INFO()
        if not kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(info)):
            return ""
        width, height = info.dwSize.X, min(info.dwCursorPosition.Y + 1, info.dwSize.Y)
        rows = []
        for y in range(height):
            buffer = ctypes.create_unicode_buffer(width)
            read = wintypes.DWORD()
            kernel32.ReadConsoleOutputCharacterW(handle, buffer, width, COORD(0, y), ctypes.byref(read))
            rows.append(buffer.value[:read.value])
    finally:
        kernel32.CloseHandle(handle)
    text = []
    for row in rows:
        text.append(row.rstrip() + ("" if len(row.rstrip()) >= width else "\n"))
    return "".join(text)
