"""ECOBuild のエージェントの窓のリング受信係：Ring II を Raw Input で受信し、ジェスチャーを JSON 行で出力する
（標準ライブラリのみ。Electron の main が子プロセスで動かす：agents/ring.js）。

モード:
  --serve       アプリ用。stdout にイベント、stdin からコマンド（前面のアプリへのキー送信など）
  --calibrate   各操作を実機で登録して、登録表（--table）に保存する
  --monitor     受信した操作の特徴と判定結果を表示（調査用）
  --find        つながっている Ring II の識別子（Bluetooth のアドレス）を探して JSON で出す
  --resident    常駐（PC にサインインしたときに窓なしで起動する）。ECOBuild が閉じている間だけ、リングの入力
                （カーソル移動・クリック・音量など）を止め、接続を保ち、押し込みで ECOBuild を起動する。
                ECOBuild が動いている間は待つ（ECOBuild 自身の受信係が受け持つ）
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
import queue
import re
import struct
import subprocess
import sys
import threading
import time

from gestures import Segmenter, build_table, classify, describe, is_release, mouse_event, signature, signed

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE_PATH = os.path.join(HERE, 'gestures.json')   # main() が --table で置き換える（アプリの設定の場所）
RING_VID_PID = 'vid&0205ac_pid&022c'               # Ring II のデバイスパスに含まれる（--find で探す）
LABELS = {'up': '上スワイプ', 'down': '下スワイプ', 'left': '左スワイプ',
          'right': '右スワイプ', 'click': 'クリック（押し込み）',
          'hold_left': '左長押し', 'hold_right': '右長押し', 'tap': 'タッチ（触れるだけ）'}

U = C.WinDLL('user32', use_last_error=True)
K = C.WinDLL('kernel32', use_last_error=True)
H = C.WinDLL('hid', use_last_error=True)
LRESULT = C.c_ssize_t
WNDPROC = C.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
HOOKPROC = C.WINFUNCTYPE(LRESULT, C.c_int, W.WPARAM, W.LPARAM)

WM_INPUT, WM_INPUT_DEVICE_CHANGE, WM_MOUSEMOVE, WM_APP = 0x00FF, 0x00FE, 0x0200, 0x8000
RIDEV_INPUTSINK, RIDEV_DEVNOTIFY, RIDEV_REMOVE = 0x100, 0x2000, 0x1
RID_INPUT, RIDI_DEVICENAME, RIDI_DEVICEINFO = 0x10000003, 0x20000007, 0x2000000B
RIM_TYPEHID = 2
WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
LLMHF_INJECTED, LLKHF_INJECTED = 0x1, 0x10
INPUT_KEYBOARD, KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 1, 0x1, 0x2
VK_LWIN, VK_MENU, VK_H = 0x5B, 0x12, 0x48
QS_ALLINPUT, PM_REMOVE = 0x04FF, 1
GENERIC_READ, FILE_SHARE_READ_WRITE, OPEN_EXISTING = 0x80000000, 0x3, 3
HIDP_INPUT, HIDP_STATUS_SUCCESS = 0, 0x00110000
MAGIC = 0x52494E47  # 自分で送ったキーの目印（'RING'。フックで止めない）
FAIL = 0xFFFFFFFF
INVALID_HANDLE = C.c_void_p(-1).value
# Consumer Control から Windows が作るキー（ブラウザー・音量・メディア・起動）。リング由来ならフックで止める
RING_KEYS = range(0xA6, 0xB8)
RING_KEY_WINDOW = 0.15  # リングの Consumer Control レポートからこの秒数内のキーはリング由来とみなす


class Device(C.Structure):
    _fields_ = [('handle', W.HANDLE), ('type', W.DWORD)]

class Registration(C.Structure):
    _fields_ = [('page', W.USHORT), ('usage', W.USHORT), ('flags', W.DWORD), ('window', W.HWND)]

class Header(C.Structure):
    _fields_ = [('type', W.DWORD), ('size', W.DWORD), ('device', W.HANDLE), ('wparam', W.WPARAM)]

class WindowClass(C.Structure):
    _fields_ = [('style', W.UINT), ('proc', WNDPROC), ('cls_extra', C.c_int),
                ('wnd_extra', C.c_int), ('instance', W.HINSTANCE), ('icon', W.HICON),
                ('cursor', W.HANDLE), ('background', W.HBRUSH),
                ('menu', W.LPCWSTR), ('name', W.LPCWSTR)]

class MouseHook(C.Structure):
    _fields_ = [('pt', W.POINT), ('data', W.DWORD), ('flags', W.DWORD),
                ('time', W.DWORD), ('extra', C.c_size_t)]

class KeyHook(C.Structure):
    _fields_ = [('vk', W.DWORD), ('scan', W.DWORD), ('flags', W.DWORD),
                ('time', W.DWORD), ('extra', C.c_size_t)]

class KeyInput(C.Structure):
    _fields_ = [('vk', W.WORD), ('scan', W.WORD), ('flags', W.DWORD),
                ('time', W.DWORD), ('extra', C.c_size_t)]

class MouseInput(C.Structure):
    _fields_ = [('dx', W.LONG), ('dy', W.LONG), ('data', W.DWORD), ('flags', W.DWORD),
                ('time', W.DWORD), ('extra', C.c_size_t)]

class InputUnion(C.Union):
    _fields_ = [('mi', MouseInput), ('ki', KeyInput)]

class Input(C.Structure):
    _fields_ = [('type', W.DWORD), ('u', InputUnion)]

class HidCaps(C.Structure):
    _fields_ = [('usage', W.USHORT), ('page', W.USHORT), ('input_length', W.USHORT),
                ('output_length', W.USHORT), ('feature_length', W.USHORT), ('reserved', W.USHORT * 17),
                ('link_nodes', W.USHORT), ('input_button_caps', W.USHORT), ('input_value_caps', W.USHORT),
                ('input_indices', W.USHORT), ('other', W.USHORT * 6)]


def bind(dll, name, restype, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = restype, args
    return fn

device_list = bind(U, 'GetRawInputDeviceList', W.UINT, C.POINTER(Device), C.POINTER(W.UINT), W.UINT)
device_info = bind(U, 'GetRawInputDeviceInfoW', W.UINT, W.HANDLE, W.UINT, C.c_void_p, C.POINTER(W.UINT))
raw_data = bind(U, 'GetRawInputData', W.UINT, W.HANDLE, W.UINT, C.c_void_p, C.POINTER(W.UINT), W.UINT)
raw_buffer = bind(U, 'GetRawInputBuffer', W.UINT, C.c_void_p, C.POINTER(W.UINT), W.UINT)
post_message = bind(U, 'PostMessageW', W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
register = bind(U, 'RegisterRawInputDevices', W.BOOL, C.POINTER(Registration), W.UINT, W.UINT)
default_proc = bind(U, 'DefWindowProcW', LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
register_class = bind(U, 'RegisterClassW', W.ATOM, C.POINTER(WindowClass))
create_window = bind(U, 'CreateWindowExW', W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                     C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p)
peek = bind(U, 'PeekMessageW', W.BOOL, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT)
translate = bind(U, 'TranslateMessage', W.BOOL, C.POINTER(W.MSG))
dispatch = bind(U, 'DispatchMessageW', LRESULT, C.POINTER(W.MSG))
msg_wait = bind(U, 'MsgWaitForMultipleObjects', W.DWORD, W.DWORD, C.c_void_p, W.BOOL, W.DWORD, W.DWORD)
destroy = bind(U, 'DestroyWindow', W.BOOL, W.HWND)
set_hook = bind(U, 'SetWindowsHookExW', W.HHOOK, C.c_int, HOOKPROC, W.HINSTANCE, W.DWORD)
next_hook = bind(U, 'CallNextHookEx', LRESULT, W.HHOOK, C.c_int, W.WPARAM, W.LPARAM)
unhook = bind(U, 'UnhookWindowsHookEx', W.BOOL, W.HHOOK)
send_input = bind(U, 'SendInput', W.UINT, W.UINT, C.POINTER(Input), C.c_int)
foreground = bind(U, 'GetForegroundWindow', W.HWND)
set_foreground = bind(U, 'SetForegroundWindow', W.BOOL, W.HWND)
bring_to_top = bind(U, 'BringWindowToTop', W.BOOL, W.HWND)
show_window = bind(U, 'ShowWindow', W.BOOL, W.HWND, C.c_int)
is_iconic = bind(U, 'IsIconic', W.BOOL, W.HWND)
is_window = bind(U, 'IsWindow', W.BOOL, W.HWND)
window_thread = bind(U, 'GetWindowThreadProcessId', W.DWORD, W.HWND, C.POINTER(W.DWORD))
attach_input = bind(U, 'AttachThreadInput', W.BOOL, W.DWORD, W.DWORD, W.BOOL)
current_thread = bind(K, 'GetCurrentThreadId', W.DWORD)
module = bind(K, 'GetModuleHandleW', W.HMODULE, W.LPCWSTR)
create_file = bind(K, 'CreateFileW', W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE)
read_file = bind(K, 'ReadFile', W.BOOL, W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p)
close_handle = bind(K, 'CloseHandle', W.BOOL, W.HANDLE)
get_preparsed = bind(H, 'HidD_GetPreparsedData', W.BOOLEAN, W.HANDLE, C.POINTER(C.c_void_p))
free_preparsed = bind(H, 'HidD_FreePreparsedData', W.BOOLEAN, C.c_void_p)
hidp_caps = bind(H, 'HidP_GetCaps', C.c_long, C.c_void_p, C.POINTER(HidCaps))
hidp_value_caps = bind(H, 'HidP_GetValueCaps', C.c_long, C.c_int, C.c_void_p, C.POINTER(W.USHORT), C.c_void_p)
hidp_usages = bind(H, 'HidP_GetUsages', C.c_long, C.c_int, W.USHORT, W.USHORT, C.POINTER(W.USHORT),
                   C.POINTER(W.ULONG), C.c_void_p, C.c_void_p, W.ULONG)
hidp_value = bind(H, 'HidP_GetUsageValue', C.c_long, C.c_int, W.USHORT, W.USHORT, W.USHORT,
                  C.POINTER(W.ULONG), C.c_void_p, C.c_void_p, W.ULONG)


def check(value):
    if value == FAIL:
        raise C.WinError(C.get_last_error())
    return value


def device_name(handle):
    size = W.UINT()
    check(device_info(handle, RIDI_DEVICENAME, None, C.byref(size)))
    buf = C.create_unicode_buffer(size.value + 1)
    check(device_info(handle, RIDI_DEVICENAME, buf, C.byref(size)))
    return buf.value


def ring_devices(match):
    """リングの Raw Input デバイス [(ハンドル, 種類, パス)]。"""
    count = W.UINT()
    check(device_list(None, C.byref(count), C.sizeof(Device)))
    items = (Device * count.value)()
    n = check(device_list(items, C.byref(count), C.sizeof(Device)))
    found = []
    for dev in items[:n]:
        try:
            path = device_name(dev.handle)
        except OSError:
            continue
        if match in path.lower():
            found.append((dev.handle, dev.type, path))
    return found


def ring_present(match):
    return bool(ring_devices(match))


def hid_usage(handle):
    """HID デバイスのトップレベルコレクションの (Usage Page, Usage)。"""
    buf = C.create_string_buffer(32)
    struct.pack_into('<I', buf, 0, 32)
    size = W.UINT(32)
    check(device_info(handle, RIDI_DEVICEINFO, buf, C.byref(size)))
    return struct.unpack_from('<HH', buf, 20)


# ---- キー送信・フォーカス ----

EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B}


def press(*vks):
    seq = [(vk, 0) for vk in vks] + [(vk, KEYEVENTF_KEYUP) for vk in reversed(vks)]
    items = (Input * len(seq))()
    for item, (vk, flags) in zip(items, seq):
        item.type = INPUT_KEYBOARD
        item.u.ki = KeyInput(vk, 0, flags | (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0), 0, MAGIC)
    send_input(len(seq), items, C.sizeof(Input))


KEY_NAMES = {
    'ctrl': 0x11, 'shift': 0x10, 'alt': 0x12, 'win': 0x5B,
    'enter': 0x0D, 'esc': 0x1B, 'tab': 0x09, 'space': 0x20, 'backspace': 0x08, 'delete': 0x2E,
    'insert': 0x2D, 'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27, 'printscreen': 0x2C,
    'volumeup': 0xAF, 'volumedown': 0xAE, 'mute': 0xAD,
    'playpause': 0xB3, 'nexttrack': 0xB0, 'prevtrack': 0xB1,
    **{chr(c).lower(): c for c in range(0x41, 0x5B)}, **{str(d): 0x30 + d for d in range(10)},
    **{f'f{n}': 0x6F + n for n in range(1, 25)},
}


def press_combo(combo):
    """'ctrl+shift+t' のような組み合わせを前面のアプリへ送る。"""
    vks = [KEY_NAMES.get(name.strip().lower()) for name in combo.split('+')]
    if not vks or None in vks:
        raise ValueError(f'unknown key: {combo}')
    press(*vks)


def bring_forward(hwnd):
    """他アプリが前面にあっても対象ウィンドウを前面化する。"""
    if not hwnd or not is_window(hwnd):
        return
    if is_iconic(hwnd):
        show_window(hwnd, 9)  # SW_RESTORE
    fg = foreground()
    if fg == hwnd:
        return
    me, other = current_thread(), window_thread(fg, None) if fg else 0
    attached = bool(other and other != me and attach_input(me, other, True))
    try:
        bring_to_top(hwnd)
        set_foreground(hwnd)
    finally:
        if attached:
            attach_input(me, other, False)
    if foreground() != hwnd:
        press(VK_MENU)  # 最後の入力を自プロセスにして前面化の制限を外す
        set_foreground(hwnd)
    log('foreground', 'ok' if foreground() == hwnd else 'failed')


# ---- カーソル保護（低レベルフック） ----

class Guard:
    """リングのマウス入力（カーソル移動・クリック・ドラッグ）を Windows に届く前に止める。

    低レベルフックではデバイスを区別できないので、2つの手がかりを組み合わせる（2026-10-15 の計測による）。
      1. 動きの形: リングの操作は必ず「左上へ一瞬で大きく飛ぶ移動」から始まる。
         この1つ目は、フックが呼ばれた時点ではまだリングの Raw Input が届いていないので形で見分ける。
      2. デバイス: 2つ目以降（位置合わせ・押下・ドラッグ・解放）は、フックの時点で直前 15〜47ms 以内に
         リングの Raw Input が届いている。直前 RING_WINDOW 秒以内にリングのマウス信号があれば止める。
    1つ目を見逃しても（カーソルが元から左上付近にある）、押下やドラッグは 2 で止まるので、カーソルが角に寄るだけで済む。
    本物のマウスが止まるのは、リングの信号が続いている間（0.15 秒程度）だけ。
    Raw Input はフックで止めても届くので、ジェスチャー判定には影響しない。
    """

    JUMP = 300           # 1イベントで左上へこれ以上（px）動いたらリングの位置合わせとみなす
    HOLD = 0.08          # 飛ぶ動きを見つけてから、リングの信号が届くまで止めておく秒数
    RING_WINDOW = 0.08   # 直前この秒数以内にリングのマウス信号があれば、その動きはリング由来とみなす
    LIMIT = 1.0          # 1回の保護の上限秒数（本物のマウスを止め続けないための安全装置）

    def __init__(self, block_vks=(), mouse=True):
        self.block_vks = set(block_vks)
        self.mouse_enabled = mouse
        self.mouse_active = True  # 専用モード（リングのマウスが OS に届かない）では止める必要がない
        self.ring = None          # 設定するとリング由来のキー（音量など）を止める
        self.ring_keys = set()    # リング由来として押下を止めたキー（リピートと解放も止める）
        self.until = self.started = 0.0
        self.last = None
        self.keys = []  # キャリブレーション用: (時刻, vk)
        self.hooks = []
        self._procs = [HOOKPROC(self._mouse), HOOKPROC(self._keyboard)]

    def install(self):
        instance = module(None)
        if self.mouse_enabled:
            self.hooks.append(set_hook(WH_MOUSE_LL, self._procs[0], instance, 0))
        self.hooks.append(set_hook(WH_KEYBOARD_LL, self._procs[1], instance, 0))

    def uninstall(self):
        for hook in self.hooks:
            if hook:
                unhook(hook)
        self.hooks = []

    def _mouse(self, code, wparam, lparam):
        if code == 0:
            info = MouseHook.from_address(lparam)
            if not info.flags & LLMHF_INJECTED and self.mouse_active:
                now = time.monotonic()
                pt = (info.pt.x, info.pt.y)
                if self.ring:
                    self.ring.drain()  # キューに残っているリングの Raw Input を先に読む
                ring_recent = self.ring is not None and now - self.ring.mouse_at < self.RING_WINDOW
                jump = False
                if wparam == WM_MOUSEMOVE and self.last:
                    dx, dy = pt[0] - self.last[0], pt[1] - self.last[1]
                    jump = dx <= -self.JUMP and dy <= -self.JUMP
                if (jump or ring_recent) and now >= self.until:
                    self.started = now  # 新しい保護区間の始まり
                if jump or ring_recent or now < self.until:
                    if now - self.started < self.LIMIT:
                        self.until = max(self.until, now + self.HOLD)
                        return 1
                self.last = pt
        return next_hook(None, code, wparam, lparam)

    def _keyboard(self, code, wparam, lparam):
        if code == 0:
            info = KeyHook.from_address(lparam)
            # リングの音量などのキーは Windows のサービスが合成して送るので、injected でもチェックする。
            # 除外するのは自分で送ったキー（MAGIC）だけ
            if info.extra != MAGIC:
                down = wparam in (0x100, 0x104)  # WM_KEYDOWN / WM_SYSKEYDOWN
                if down:
                    self.keys.append((time.monotonic(), info.vk))
                    del self.keys[:-50]
                if info.vk in RING_KEYS:
                    log('media key', f'vk={info.vk:#x} down={down} injected={bool(info.flags & LLKHF_INJECTED)}')
                if info.vk in self.block_vks or self._from_ring(info.vk, down):
                    return 1
        return next_hook(None, code, wparam, lparam)

    def _from_ring(self, vk, down):
        """リングの Consumer Control から Windows が作ったキーか。

        フックが呼ばれた時点では同じ操作の Raw Input がまだキューに残っていることがあるので、先に読んでから判定する。
        """
        if vk in self.ring_keys:
            if not down:
                self.ring_keys.discard(vk)
            return True
        if not self.ring or not down or vk not in RING_KEYS:
            return False
        self.ring.drain()
        ago = time.monotonic() - self.ring.consumer_at
        blocked = ago < RING_KEY_WINDOW
        log('key', f'vk={vk:#x} ring_report_ago={ago:.3f} blocked={blocked}')
        if blocked:
            self.ring_keys.add(vk)
        return blocked

    def keys_between(self, start, end):
        return sorted({vk for t, vk in self.keys if start - 0.3 <= t <= end + 0.3})


# ---- Raw Input ----

class RingInput:
    def __init__(self, match, on_event):
        self.match = match.lower()
        self.on_event = on_event
        self.targets, self.others = set(), set()
        self.consumer_at = -1.0       # 最後にリングの Consumer Control レポートを受けた時刻
        self.mouse_at = -1.0          # 最後にリングのマウス信号（Raw Input）を受けた時刻
        self.readers = {}             # 専用モード: パス → HidMouse
        self.pending = queue.Queue()  # HidMouse のスレッドから届いたイベント
        self._proc = WNDPROC(self._wndproc)
        instance = module(None)
        cls = WindowClass()
        cls.proc, cls.instance, cls.name = self._proc, instance, 'ECOBuildRingListener'
        if not register_class(C.byref(cls)):
            raise C.WinError(C.get_last_error())
        self.hwnd = create_window(0, cls.name, '', 0, 0, 0, 0, 0, None, None, instance, None)
        if not self.hwnd:
            raise C.WinError(C.get_last_error())
        flags = RIDEV_INPUTSINK | RIDEV_DEVNOTIFY
        self.regs = (Registration * 2)(Registration(0x01, 0x02, flags, self.hwnd),
                                       Registration(0x0C, 0x01, flags, self.hwnd))
        if not register(self.regs, 2, C.sizeof(Registration)):
            raise C.WinError(C.get_last_error())
        self.changed = True

    def scan(self):
        """専用モードのマウス用コレクション（OS のマウスではなく HID として見える）を探して読み始める。"""
        found = set()
        for handle, kind, path in ring_devices(self.match):
            if kind != RIM_TYPEHID:
                continue
            try:
                if hid_usage(handle) != (0x01, 0x02):
                    continue
            except OSError:
                continue
            found.add(path)
            reader = self.readers.get(path)
            if reader is None or not reader.alive:
                try:
                    self.readers[path] = HidMouse(path, self.post)
                    log('hid open', path)
                except OSError as exc:
                    log('hid open failed', f'{path} {exc}')
        for path in list(self.readers):
            if path not in found or not self.readers[path].alive:
                del self.readers[path]
        return bool(self.readers)

    def post(self, event):
        """別スレッドからイベントを渡す（メッセージループで受け取る）。"""
        self.pending.put(event)
        post_message(self.hwnd, WM_APP, 0, 0)

    def drain(self):
        """キューに残っている Raw Input をメッセージを待たずに読む（キーボードフックから使う）。"""
        size = W.UINT()
        if raw_buffer(None, C.byref(size), C.sizeof(Header)) == FAIL or not size.value:
            return
        size.value *= 32
        buf = C.create_string_buffer(size.value)
        count = raw_buffer(buf, C.byref(size), C.sizeof(Header))
        if count in (0, FAIL):
            return
        offset = 0
        for _ in range(count):
            header = Header.from_buffer(buf, offset)
            self._handle(header, buf.raw[offset + C.sizeof(Header):offset + header.size])
            offset += (header.size + 7) & ~7

    def close(self):
        for reg in self.regs:
            reg.flags, reg.window = RIDEV_REMOVE, None
        register(self.regs, 2, C.sizeof(Registration))
        destroy(self.hwnd)

    def _is_target(self, handle):
        if handle in self.targets:
            return True
        if handle in self.others:
            return False
        try:
            path = device_name(handle).lower()
        except OSError:
            return False
        (self.targets if self.match in path else self.others).add(handle)
        return handle in self.targets

    def _wndproc(self, hwnd, message, wparam, lparam):
        if message == WM_INPUT:
            try:
                self._read(lparam)
            except Exception as exc:
                emit(event='error', message=f'raw input: {exc}')
        elif message == WM_INPUT_DEVICE_CHANGE:
            self.targets.clear()
            self.others.clear()
            self.changed = True
        elif message == WM_APP:
            while not self.pending.empty():
                self.on_event(self.pending.get())
        return default_proc(hwnd, message, wparam, lparam)

    def _read(self, lparam):
        size = W.UINT()
        check(raw_data(lparam, RID_INPUT, None, C.byref(size), C.sizeof(Header)))
        buf = C.create_string_buffer(size.value)
        check(raw_data(lparam, RID_INPUT, buf, C.byref(size), C.sizeof(Header)))
        self._handle(Header.from_buffer(buf), buf.raw[C.sizeof(Header):size.value])

    def _handle(self, header, payload):
        if not self._is_target(header.device):
            return
        if header.type == 0 and len(payload) >= 24:
            self.mouse_at = time.monotonic()
            flags, buttons, _ = struct.unpack_from('<H2xHH', payload)
            x, y = struct.unpack_from('<ii', payload, 12)
            self.on_event({'kind': 'mouse', 'x': x, 'y': y, 'buttons': buttons, 'flags': flags})
        elif header.type == 2 and len(payload) >= 8:
            report_size, count = struct.unpack_from('<II', payload)
            for i in range(count):
                report = payload[8 + i * report_size:8 + (i + 1) * report_size].hex()
                self.consumer_at = time.monotonic()
                self.on_event({'kind': 'hid', 'report': report})


class HidMouse:
    """専用モードのマウス用コレクションを ReadFile で直接読み、Raw Input と同じ形のイベントを渡す。

    ドライバーを "HID-compliant device" に差し替えたコレクションは OS のマウスではないので、
    カーソルやクリックにならず、Raw Input のマウスとしても届かない（ring/exclusive.ps1）。
    読み取りが失敗したら（切断・ドライバーを戻した）スレッドを終える。次のデバイス変化で開き直す。
    """

    def __init__(self, path, on_event):
        if path.startswith('\\??\\'):
            path = '\\\\?\\' + path[4:]
        self.on_event = on_event
        self.handle = create_file(path, GENERIC_READ, FILE_SHARE_READ_WRITE, None, OPEN_EXISTING, 0, None)
        if self.handle in (None, INVALID_HANDLE):
            raise C.WinError(C.get_last_error())
        self.preparsed = C.c_void_p()
        if not get_preparsed(self.handle, C.byref(self.preparsed)):
            error = C.get_last_error()
            close_handle(self.handle)
            raise C.WinError(error)
        caps = HidCaps()
        hidp_caps(self.preparsed, C.byref(caps))
        self.length = caps.input_length
        self.axes = self._axes(caps.input_value_caps)
        self.pressed = set()
        self.alive = True
        threading.Thread(target=self._run, daemon=True).start()

    def _axes(self, count):
        """X / Y の [(Usage, リンクコレクション, ビット数, 符号付きか)]。HIDP_VALUE_CAPS は 72 バイト。"""
        n = W.USHORT(count)
        buf = C.create_string_buffer(72 * max(count, 1))
        if hidp_value_caps(HIDP_INPUT, buf, C.byref(n), self.preparsed) != HIDP_STATUS_SUCCESS:
            return []
        axes = []
        for i in range(n.value):
            base = i * 72
            page, = struct.unpack_from('<H', buf, base)
            link, = struct.unpack_from('<H', buf, base + 6)
            is_range = buf.raw[base + 12]
            bits, = struct.unpack_from('<H', buf, base + 18)
            logical_min, = struct.unpack_from('<i', buf, base + 40)
            low, high = struct.unpack_from('<HH', buf, base + 56)
            for usage in (0x30, 0x31):
                if page == 0x01 and (low <= usage <= high if is_range else low == usage):
                    axes.append((usage, link, bits, logical_min < 0))
        return axes

    def _run(self):
        buf = C.create_string_buffer(self.length)
        read = W.DWORD()
        try:
            while read_file(self.handle, buf, self.length, C.byref(read), None):
                self._report(buf, read.value)
        finally:
            self.alive = False
            log('hid closed', C.get_last_error())
            free_preparsed(self.preparsed)
            close_handle(self.handle)

    def _report(self, buf, length):
        usages = (W.USHORT * 16)()
        n = W.ULONG(16)
        if hidp_usages(HIDP_INPUT, 0x09, 0, usages, C.byref(n), self.preparsed, buf, length) == HIDP_STATUS_SUCCESS:
            pressed = set(usages[:n.value])
        else:
            pressed = self.pressed  # このレポートにボタンが含まれない
        move = {0x30: 0, 0x31: 0}
        for usage, link, bits, is_signed in self.axes:
            value = W.ULONG()
            if hidp_value(HIDP_INPUT, 0x01, link, usage, C.byref(value), self.preparsed, buf, length) == HIDP_STATUS_SUCCESS:
                move[usage] = signed(value.value, bits) if is_signed else value.value
        if pressed == self.pressed and not any(move.values()):
            return
        event = mouse_event(self.pressed, pressed, move[0x30], move[0x31])
        self.pressed = pressed
        self.on_event(event)


# ---- 実行 ----

_out_lock = threading.Lock()
_log_file = None


def open_log(path):
    global _log_file
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _log_file = open(path, 'w', encoding='utf-8')


def log(kind, detail=''):
    if _log_file:
        with _out_lock:
            _log_file.write(f'{time.strftime("%H:%M:%S")}.{int(time.time() * 1000) % 1000:03d} '
                            f'{kind} {detail}\n')
            _log_file.flush()


def emit(**value):
    log('emit', value)
    with _out_lock:
        print(json.dumps(value, ensure_ascii=True), flush=True)


def load_table():
    try:
        with open(TABLE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {'gestures': {}, 'block_vks': []}


def table_mtime():
    try:
        return os.path.getmtime(TABLE_PATH)
    except OSError:
        return None


def save_table(data):
    with open(TABLE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---- 常駐（--resident） ----
# ECOBuild が動いているかは、ECOBuild が起動時に書くファイル（--running：プロセスの番号）で見る。ECOBuild は終わっても
# このファイルを消さない（終わる途中で消すと、まだ残っているうちに新しく起動してしまう）ので、その番号のプロセスが
# 生きていて、実行ファイルの名前が ECOBuild の GUI のものかも確かめる。起動するコマンドは --launch（JSON の並び）。
open_process = bind(K, 'OpenProcess', W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
exit_code = bind(K, 'GetExitCodeProcess', W.BOOL, W.HANDLE, C.POINTER(W.DWORD))
create_mutex = bind(K, 'CreateMutexW', W.HANDLE, C.c_void_p, W.BOOL, W.LPCWSTR)
image_name = bind(K, 'QueryFullProcessImageNameW', W.BOOL, W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD))
STILL_ACTIVE, PROCESS_QUERY_LIMITED_INFORMATION, ERROR_ALREADY_EXISTS = 259, 0x1000, 183
APP_IMAGES = ('electron.exe', 'ecobuild gui.exe')


def app_running(running_file):
    try:
        with open(running_file, encoding='utf-8') as f:
            pid = int(f.read().strip())
    except (OSError, ValueError, TypeError):
        return False
    handle = open_process(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = W.DWORD()
        if not (exit_code(handle, C.byref(code)) and code.value == STILL_ACTIVE):
            return False
        buf, size = C.create_unicode_buffer(1024), W.DWORD(1024)
        if not image_name(handle, 0, buf, C.byref(size)):
            return True  # 名前が取れなければ、生きていることだけで決める
        return os.path.basename(buf.value).lower() in APP_IMAGES
    finally:
        close_handle(handle)


def launch_app(command):
    """ECOBuild を起動する（このプロセスとは切り離して）。"""
    try:
        subprocess.Popen(command, creationflags=0x00000008 | 0x00000200, close_fds=True)   # DETACHED_PROCESS・NEW_PROCESS_GROUP
        return True
    except (OSError, TypeError) as exc:
        log('launch failed', exc)
        return False


def find_rings():
    """つながっている Ring II（デバイスパスに RING_VID_PID を含むもの）の識別子。パスの中の 12 桁の16進（Bluetooth の
    アドレス）を識別子にする（--match に使い、接続の維持にも使う）。"""
    found = {}
    for handle, kind, path in ring_devices(RING_VID_PID):
        address = re.search(r'([0-9a-f]{12})', path.lower().split(RING_VID_PID, 1)[-1])
        if address:
            found.setdefault(address.group(1), path)
    return [{'match': a, 'path': p} for a, p in found.items()]


class App:
    def __init__(self, args):
        self.args = args
        self.data = load_table()
        self._set_table(self.data)
        self.table_mtime = table_mtime()
        self.next_reload = 0.0
        self.seg = Segmenter(args.gap)
        self.guard = Guard(self.data.get('block_vks', []) if args.mode != 'calibrate' else [],
                           mouse=not args.no_guard)
        self.ring = RingInput(args.match, self._on_event)
        if args.mode != 'calibrate':
            self.guard.ring = self.ring
        self.next_scan = 0.0
        self.running = True
        self.commands = queue.Queue()
        self.present = None
        self.handled = False
        self.last_report = None
        self.app_up = None           # 常駐：ECOBuild が動いているか（None はまだ調べていない）
        self.next_app_check = 0.0
        self.launch_cooldown = 0.0
        self.keepalive = None
        if args.mode == 'calibrate':
            self.plan = [g for g in args.gestures for _ in range(args.repeat)]
            self.samples = {g: [] for g in args.gestures}
            self.vks = set()

    def _set_table(self, data):
        self.table = data.get('gestures', {})
        self.invert_drag = data.get('invert_drag', False)
        # リングのモード（LED の色）で信号が変わる操作。管理モードの信号は "admin:click" のような名前で登録してある
        self.moded = {name.split(':', 1)[1] for name in self.table if ':' in name}

    def _emit_gesture(self, name):
        """操作を知らせる。mode はその信号から分かるリングのモード（どちらのモードでも同じ信号なら None）。"""
        if ':' in name:
            mode, name = name.split(':', 1)
        else:
            mode = 'work' if name in self.moded else None
        emit(event='gesture', gesture=name, mode=mode)

    def _on_event(self, event):
        log('in', event)
        burst = self.seg.feed(event, time.monotonic())
        if burst:
            self._on_burst(burst)
        if self.args.mode == 'serve' and event['kind'] == 'hid':
            self._on_report(event['report'])

    def _on_report(self, report):
        """押下レポートは区切りを待たずに即判定する（連続操作がまとまって未登録扱いになるのを防ぐ）。"""
        previous, self.last_report = self.last_report, report
        if is_release(report) or report == previous:
            return
        name = classify({'kind': 'hid', 'reports': [report]}, self.table)
        if name:
            self.handled = True
            self._emit_gesture(name)

    def _on_burst(self, burst):
        sig = signature(burst.events)
        mode = self.args.mode
        log('burst', describe(sig))
        if mode == 'serve':
            handled, self.handled = self.handled, False
            if sig is None or handled:
                return
            name = classify(sig, self.table, self.invert_drag)
            if name:
                self._emit_gesture(name)
            else:
                emit(event='unknown', signature=describe(sig))
        elif mode == 'resident':
            if self.app_up or sig is None:
                return
            name = classify(sig, self.table, self.invert_drag)
            log('resident gesture', name)
            if name and name.split(':')[-1] == 'click' and time.monotonic() >= self.launch_cooldown:
                self.launch_cooldown = time.monotonic() + 15.0  # 起動を待つ間に何度押しても、二重に起動しない
                log('launch', launch_app(json.loads(self.args.launch or '[]')))
        elif mode == 'monitor':
            print(f'{time.strftime("%H:%M:%S")} {describe(sig):40s} -> {classify(sig, self.table, self.invert_drag) if sig else "-"}', flush=True)
        else:
            self._calibrate(burst, sig)

    def _calibrate(self, burst, sig):
        if sig is None or not self.plan:
            return
        name = self.plan.pop(0)
        self.samples[name].append(sig)
        if sig['kind'] == 'hid':
            self.vks.update(self.guard.keys_between(burst.start, burst.end))
        print(f'  受信: {describe(sig)}', flush=True)
        self._prompt()

    def _prompt(self):
        if not self.plan:
            self._finish()
            return
        name = self.plan[0]
        done = len(self.samples[name])
        if done == 0:
            print(f'\n「{LABELS.get(name, name)}」を {self.args.repeat} 回、1秒ほど間を空けて行ってください。', flush=True)

    def _finish(self):
        self.running = False
        if self.args.prefix:
            self._finish_prefixed()
            return
        # 別のモードの登録（"admin:click" など。--prefix で足したもの）は残す
        kept = {k: v for k, v in load_table().get('gestures', {}).items() if ':' in k}
        try:
            table = build_table({**kept, **self.samples})
        except ValueError as exc:
            print(f'\n登録できませんでした: {exc}\nもう一度 --calibrate を実行してください。', flush=True)
            return
        save_table({'gestures': table, 'block_vks': sorted(self.vks), 'device_match': self.args.match})
        print(f'\n保存しました: {TABLE_PATH}', flush=True)
        for name, sigs in table.items():
            print(f'  {LABELS.get(name, name)}: ' + ' / '.join(describe(s) for s in sigs), flush=True)
        if self.vks:
            print(f'  アプリ実行中はリングが出すキー {[hex(v) for v in sorted(self.vks)]} を止めます。'
                  '（キーボードの同じメディアキーも止まります）', flush=True)

    def _finish_prefixed(self):
        """リングの別のモードの信号を "<prefix>:<操作>" として今の登録表に足す。

        今の登録（作業モード）と同じ信号になる操作は足さない（どちらのモードか区別できないので、アプリが持つモードに従う）。
        """
        prefix = self.args.prefix
        current = load_table()
        table = {k: v for k, v in current.get('gestures', {}).items()
                 if not (k.startswith(prefix + ':') and k.split(':', 1)[1] in self.samples)}
        base = {k: v for k, v in table.items() if ':' not in k}
        invert = current.get('invert_drag', False)
        added, same = {}, []
        for name, sigs in self.samples.items():
            differ = [s for s in sigs if s is not None and classify(s, base, invert) != name]
            if differ:
                added[f'{prefix}:{name}'] = differ
            else:
                same.append(name)
        try:
            merged = build_table({**table, **added})
        except ValueError as exc:
            print(f'\n登録できませんでした: {exc}\nもう一度実行してください。', flush=True)
            return
        vks = sorted(set(current.get('block_vks', [])) | self.vks)
        save_table({**current, 'gestures': merged, 'block_vks': vks})
        print(f'\n保存しました: {TABLE_PATH}', flush=True)
        for name in added:
            print(f'  {LABELS.get(name.split(":", 1)[1])}（{prefix}）: ' + ' / '.join(describe(s) for s in merged[name]), flush=True)
        if same:
            print('  今のモードと同じ信号（モードで区別できない）: ' + '、'.join(LABELS.get(n, n) for n in same), flush=True)

    def _read_stdin(self):
        for line in sys.stdin:
            try:
                self.commands.put(json.loads(line))
            except ValueError:
                pass
        self.commands.put({'cmd': 'quit'})

    def _handle(self, cmd):
        log('cmd', cmd)
        name = cmd.get('cmd')
        if name == 'keys':
            try:
                press_combo(cmd.get('keys', ''))
            except ValueError as exc:
                emit(event='error', message=str(exc))
        elif name == 'keepalive':
            self._start_keepalive() if cmd.get('on') else self._stop_keepalive()
        elif name == 'quit':
            self.running = False

    def _reload_table(self):
        """gestures.json が書き換えられたら読み直す（アプリを再起動せずに反映する）。"""
        self.next_reload = time.monotonic() + 1.0
        mtime = table_mtime()
        if mtime == self.table_mtime:
            return
        self.table_mtime = mtime
        self.data = load_table()
        self._set_table(self.data)
        self.guard.block_vks = set(self.data.get('block_vks', []))
        log('reload', TABLE_PATH)

    def _status(self):
        # 専用モードの切り替え（ドライバーの差し替え）は Raw Input の通知に出ないことがあるので定期的にも見る
        self.next_scan = time.monotonic() + 3.0
        present = ring_present(self.ring.match)
        exclusive = self.ring.scan()
        self.guard.mouse_active = not exclusive
        if (present, exclusive) != self.present:
            self.present = (present, exclusive)
            if self.args.mode == 'serve':
                emit(event='status', connected=present, calibrated=bool(self.table), exclusive=exclusive)
            elif not present:
                print('Ring II が見つかりません。本体を操作して起こしてください。', flush=True)
            else:
                print('マウス入力: ' + ('専用（OS には届かない）' if exclusive else 'OS にも届く（カーソルの動き・クリックはここで止める）'), flush=True)

    def _check_app(self):
        """常駐：ECOBuild の起動・終了に合わせて、フックの付け外しと接続の維持を切り替える。設定のファイルが
        なくなったら（常駐をやめた）終わる。"""
        self.next_app_check = time.monotonic() + 1.0
        if self.args.config and not os.path.exists(self.args.config):
            log('resident stopped', 'config removed')
            self.running = False
            return
        running = app_running(self.args.running)
        if running == self.app_up:
            return
        self.app_up = running
        log('app running', running)
        if running:
            self.guard.uninstall()
            self._stop_keepalive()
        else:
            if not self.args.no_guard:
                self.guard.install()
            self._start_keepalive()

    def _start_keepalive(self):
        if self.keepalive and self.keepalive.poll() is None:
            return
        if not re.fullmatch(r'[0-9a-f]{12}', self.args.match.lower()):
            return   # 接続の維持には Bluetooth のアドレスが要る（--find の識別子）
        script = os.path.join(HERE, 'keepalive.ps1')
        self.keepalive = subprocess.Popen(
            ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script,
             '-Address', self.args.match.upper(), '-ParentPid', str(os.getpid())],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=0x08000000, text=True)  # CREATE_NO_WINDOW
        threading.Thread(target=self._read_keepalive, args=(self.keepalive,), daemon=True).start()

    def _read_keepalive(self, proc):
        """接続の維持の知らせ（接続・電池残量）をそのまま伝える。"""
        for line in proc.stdout:
            try:
                emit(event='ble', **json.loads(line))
            except (ValueError, TypeError):
                pass

    def _stop_keepalive(self):
        if self.keepalive and self.keepalive.poll() is None:
            self.keepalive.terminate()
        self.keepalive = None

    def run(self):
        mode = self.args.mode
        if mode == 'serve':
            threading.Thread(target=self._read_stdin, daemon=True).start()
        elif mode == 'calibrate':
            print('キャリブレーションを始めます。Ctrl+C で中止。', flush=True)
            self._prompt()
        elif mode != 'resident':
            print('受信中。Ring II を操作してください。Ctrl+C で終了。', flush=True)
        if mode != 'resident':
            self.guard.install()   # 常駐は ECOBuild が閉じている間だけ付ける（_check_app）
        msg = W.MSG()
        try:
            while self.running:
                msg_wait(0, None, False, 40, QS_ALLINPUT)
                while peek(C.byref(msg), None, 0, 0, PM_REMOVE):
                    translate(C.byref(msg))
                    dispatch(C.byref(msg))
                burst = self.seg.poll(time.monotonic())
                if burst:
                    self._on_burst(burst)
                if self.args.mode != 'calibrate' and time.monotonic() >= self.next_reload:
                    self._reload_table()
                if self.ring.changed or time.monotonic() >= self.next_scan:
                    self.ring.changed = False
                    self._status()
                while not self.commands.empty():
                    self._handle(self.commands.get())
                if mode == 'resident' and time.monotonic() >= self.next_app_check:
                    self._check_app()
        except KeyboardInterrupt:
            pass
        finally:
            self.guard.uninstall()
            self._stop_keepalive()
            self.ring.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--serve', dest='mode', action='store_const', const='serve')
    group.add_argument('--calibrate', dest='mode', action='store_const', const='calibrate')
    group.add_argument('--monitor', dest='mode', action='store_const', const='monitor')
    group.add_argument('--find', dest='mode', action='store_const', const='find')
    group.add_argument('--resident', dest='mode', action='store_const', const='resident')
    parser.add_argument('--running', help='常駐：ECOBuild が動いている間、そのプロセスの番号が書いてあるファイル')
    parser.add_argument('--launch', help='常駐：押し込みで ECOBuild を起動するコマンド（JSON の並び）')
    parser.add_argument('--config', help='常駐：設定のファイル（JSON：match・table・running・launch・guard・keepalive）。'
                                         'このファイルを消すと常駐も終わる')
    parser.add_argument('--match', default=RING_VID_PID, help='対象デバイスパスに含まれる文字列（--find の識別子）')
    parser.add_argument('--table', help='登録表（ジェスチャーの登録）のファイル')
    parser.add_argument('--log', help='記録のファイル（serve・monitor）')
    parser.add_argument('--keepalive', action='store_true', help='Ring II との接続を維持するよう Windows に頼み続ける（serve）')
    parser.add_argument('--gestures', nargs='+', default=['up', 'down', 'click'],
                        choices=sorted(LABELS), help='キャリブレーションする操作')
    parser.add_argument('--prefix', help='リングの別のモードの信号として "<prefix>:<操作>" の名前で今の登録に足す（例 admin）')
    parser.add_argument('--repeat', type=int, default=3, help='キャリブレーションで各操作を行う回数')
    parser.add_argument('--gap', type=float, default=0.18, help='操作の区切りとみなす無入力時間（秒）')
    parser.add_argument('--no-guard', action='store_true', help='カーソル保護フックを使わない')
    parser.set_defaults(mode='monitor')
    args = parser.parse_args()
    if args.config:
        try:
            with open(args.config, encoding='utf-8') as f:
                config = json.load(f)
        except (OSError, ValueError):
            return
        args.match = config.get('match') or args.match
        args.table = config.get('table') or args.table
        args.running = config.get('running') or args.running
        args.launch = json.dumps(config.get('launch') or [])
        args.no_guard = config.get('guard') is False
        args.keepalive = config.get('keepalive') is not False
        args.log = config.get('log') or args.log
    global TABLE_PATH
    if args.table:
        TABLE_PATH = args.table
        os.makedirs(os.path.dirname(TABLE_PATH) or '.', exist_ok=True)
    if args.log and args.mode in ('serve', 'monitor', 'resident'):
        open_log(args.log)
    if args.mode == 'resident':
        # サインインごとに1つだけ（スタートアップと手で起動したものが重なっても二重にしない）
        mutex = create_mutex(None, False, 'Local\\ECOBuildRingResident')
        if not mutex or C.get_last_error() == ERROR_ALREADY_EXISTS:
            log('resident already running')
            return
    if args.mode == 'find':
        print(json.dumps(find_rings(), ensure_ascii=True), flush=True)
        return
    if args.mode != 'serve' and sys.stdout is not None:  # pythonw（コンソールなし）では stdout が無い
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        C.windll.user32.SetProcessDpiAwarenessContext(C.c_void_p(-4))
    except (AttributeError, OSError):
        pass
    app = App(args)
    if args.mode == 'serve' and args.keepalive:
        app._start_keepalive()
    app.run()
    if args.mode == 'calibrate' and sys.stdin is not None and sys.stdin.isatty():
        print()
        input('Enter で閉じます。')   # 調整は自分の窓で動く：結果を読めるように


if __name__ == '__main__':
    main()
