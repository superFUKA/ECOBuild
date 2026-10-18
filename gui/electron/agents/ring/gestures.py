"""Ring II の生入力を操作単位にまとめ、登録済みの特徴と照合する（Win32 非依存）。"""
import collections
import datetime
import json
import math

RESET = 1000          # ±2047 の位置合わせ移動を特徴量から外す閾値
DOWN_FLAGS = 0x15     # 左・右・中ボタンの押下フラグ
UP_FLAGS = 0x2A       # 同じく解放フラグ
TAP = 40              # ドラッグとみなす最小の移動量


class Segmenter:
    """イベント間隔が gap 秒以上空いたら1操作分（バースト）として区切る。"""

    def __init__(self, gap=0.18):
        self.gap = gap
        self.events = []
        self.first = self.last = None

    def feed(self, event, now):
        done = self.poll(now)
        if not self.events:
            self.first = now
        self.events.append(event)
        self.last = now
        return done

    def poll(self, now):
        if self.events and now - self.last >= self.gap:
            burst = Burst(self.events, self.first, self.last)
            self.events = []
            return burst
        return None


Burst = collections.namedtuple('Burst', 'events start end')


def is_release(report):
    return int(report[2:] or '0', 16) == 0


def signature(events):
    """操作の特徴。

    - Consumer Control のレポートがあれば: hid（レポートの組）
    - ボタンを押したまま動かしていれば: drag（押してから離すまでの移動量。開始位置は毎回ずれるので含めない）
    - それ以外: mouse（位置合わせ後の移動量の合計）
    """
    reports = sorted({e['report'] for e in events if e['kind'] == 'hid' and not is_release(e['report'])})
    if reports:
        return {'kind': 'hid', 'reports': reports}
    move = [0, 0]
    drag = [0, 0]
    pressed = button = False
    for e in events:
        if e['kind'] != 'mouse' or e.get('flags', 0) & 1:
            continue
        if e['buttons'] & DOWN_FLAGS:
            pressed = button = True
        if abs(e['x']) < RESET and abs(e['y']) < RESET:
            target = drag if pressed else move
            target[0] += e['x']
            target[1] += e['y']
        if e['buttons'] & UP_FLAGS:
            pressed = False
    if button:
        return {'kind': 'drag', 'dx': drag[0], 'dy': drag[1]}
    if move == [0, 0]:
        return None
    return {'kind': 'mouse', 'dx': move[0], 'dy': move[1], 'button': False}


def drag_direction(sig, invert=False):
    """ドラッグの向き。動きが小さい（押しただけ）なら None。

    浅いスワイプが押しただけの信号になることがあり、クリック扱いにすると音声入力が誤って始まるため無視する。

    invert: Ring II はスワイプと逆向きにドラッグする（画面を引っ張る向き）ので、指の向きに直す。
    """
    dx, dy = (-sig['dx'], -sig['dy']) if invert else (sig['dx'], sig['dy'])
    if max(abs(dx), abs(dy)) < TAP:
        return None
    if abs(dx) >= abs(dy):
        return 'right' if dx > 0 else 'left'
    return 'down' if dy > 0 else 'up'


def distance(a, b):
    """同じ操作とみなせるなら距離、みなせないなら None。"""
    if a['kind'] != b['kind']:
        return None
    if a['kind'] == 'hid':
        return 0.0 if a['reports'] == b['reports'] else None
    if a.get('button') != b.get('button'):
        return None
    d = math.hypot(a['dx'] - b['dx'], a['dy'] - b['dy'])
    return d if d <= max(40.0, 0.35 * math.hypot(b['dx'], b['dy'])) else None


def match(sig, table):
    """登録表だけで照合する。"""
    best = None
    for name, samples in table.items():
        for sample in samples:
            d = distance(sig, sample)
            if d is not None and (best is None or d < best[0]):
                best = (d, name)
    return best[1] if best else None


def classify(sig, table, invert_drag=False):
    # ドラッグは登録がなくても向きで判定する（リングのモードが変わっても動く）。
    # 動きのないドラッグ（ボタンを押して離しただけ）はタッチ面に触れただけの操作 tap。
    # 浅いスワイプでも出ることがあるので、音声入力など誤爆して困る動作は割り当てないこと
    name = match(sig, table)
    if name is None and sig['kind'] == 'drag':
        name = drag_direction(sig, invert_drag) or 'tap'
    return name


def describe(sig):
    if sig is None:
        return '(位置合わせのみ)'
    if sig['kind'] == 'hid':
        return 'hid ' + ','.join(sig['reports'])
    if sig['kind'] == 'drag':
        return f"drag dx={sig['dx']} dy={sig['dy']}"
    return f"mouse dx={sig['dx']} dy={sig['dy']}" + (' +button' if sig['button'] else '')


def build_table(samples):
    """{gesture: [sig, ...]} から重複を除いた登録表を作る。他の操作と衝突したら ValueError。"""
    table = {}
    for name, sigs in samples.items():
        unique = []
        for sig in sigs:
            if sig is not None and not any(distance(sig, u) is not None for u in unique):
                unique.append(sig)
        table[name] = unique
    for name, sigs in table.items():
        for sig in sigs:
            other = match(sig, {k: v for k, v in table.items() if k != name})
            if other:
                raise ValueError(f'「{name}」と「{other}」が区別できません: {describe(sig)}')
    return table


def events_from_capture(lines):
    """旧調査ツール（ring_input.py）の JSONL を (時刻, イベント) 列に変換する。"""
    for line in lines:
        item = json.loads(line)
        if item.get('event') != 'input':
            continue
        t = datetime.datetime.fromisoformat(item['time']).timestamp()
        if item.get('type') == 0:
            yield t, {'kind': 'mouse', 'x': item['x'], 'y': item['y'],
                      'buttons': item['button_flags'], 'flags': item['mouse_flags']}
        elif item.get('type') == 2:
            for report in item.get('reports', []):
                yield t, {'kind': 'hid', 'report': report}


def bursts(timed_events, gap=0.18):
    seg = Segmenter(gap)
    for t, event in timed_events:
        done = seg.feed(event, t)
        if done:
            yield done
    done = seg.poll(math.inf)
    if done:
        yield done


# RAWMOUSE の usButtonFlags と同じ並び（左・右・中の押下 / 解放）
BUTTON_FLAGS = [(0x01, 0x02), (0x04, 0x08), (0x10, 0x20)]


def mouse_event(previous, pressed, dx, dy):
    """HID レポートから読んだボタン状態（ボタン番号 1〜3 の集合）を Raw Input と同じ形のイベントにする。

    専用モードではマウス用コレクションを直接読むので、押下・解放のフラグは前回の状態との差分から作る。
    """
    flags = 0
    for number, (down, up) in enumerate(BUTTON_FLAGS, 1):
        if number in pressed and number not in previous:
            flags |= down
        elif number in previous and number not in pressed:
            flags |= up
    return {'kind': 'mouse', 'x': dx, 'y': dy, 'buttons': flags, 'flags': 0}


def signed(value, bits):
    """HID の値（符号なしで読める）を bits ビットの符号付き整数にする。"""
    value &= (1 << bits) - 1
    return value - (1 << bits) if value & (1 << (bits - 1)) else value
