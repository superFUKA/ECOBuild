import os
import unittest

from gestures import Segmenter, bursts, build_table, classify, events_from_capture, mouse_event, signature, signed

FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures', 'capture_2026-09-19.jsonl')


def mouse(x, y, buttons=0):
    return {'kind': 'mouse', 'x': x, 'y': y, 'buttons': buttons, 'flags': 0}


def hid(report):
    return {'kind': 'hid', 'report': report}


class SignatureTests(unittest.TestCase):
    def test_reset_moves_are_ignored(self):
        sig = signature([mouse(-2047, -2047), mouse(-2047, -2047), mouse(70, 200)])
        self.assertEqual(sig, {'kind': 'mouse', 'dx': 70, 'dy': 200, 'button': False})
        self.assertIsNone(signature([mouse(-2047, -2047)]))

    def test_drag_with_button(self):
        events = [mouse(-2047, -2047), mouse(0, 0, 1)] + [mouse(-35, 0)] * 4 + [mouse(0, 0, 2)]
        self.assertEqual(signature(events), {'kind': 'drag', 'dx': -140, 'dy': 0})

    def test_drag_ignores_start_position(self):
        # 開始位置が (70,200) でも (70,100) でも、押してから離すまでの動きで判定する
        for start in [(70, 200), (70, 100), (105, 100)]:
            events = [mouse(-2047, -2047), mouse(-2047, -2047), mouse(*start), mouse(0, 0, 1)]
            events += [mouse(0, -35)] * 4 + [mouse(0, 0, 2), mouse(-2047, -2047)]
            self.assertEqual(classify(signature(events), {}), 'up')

    def test_inverted_drag(self):
        sig = signature([mouse(0, 0, 1), mouse(0, 180), mouse(0, 0, 2)])
        self.assertEqual(classify(sig, {}, invert_drag=True), 'up')
        self.assertEqual(classify(sig, {}, invert_drag=False), 'down')

    def test_drag_directions_without_table(self):
        for dx, dy, want in [(140, 0, 'right'), (-140, 0, 'left'), (0, 130, 'down'), (0, -130, 'up'), (3, 2, 'tap'), (0, 0, 'tap')]:
            sig = signature([mouse(0, 0, 1), mouse(dx, dy), mouse(0, 0, 2)])
            self.assertEqual(classify(sig, {}), want)

    def test_release_report_is_ignored(self):
        self.assertEqual(signature([hid('03040000'), hid('03000000')]),
                         {'kind': 'hid', 'reports': ['03040000']})


class SegmentTests(unittest.TestCase):
    def test_gap_splits_bursts(self):
        seg = Segmenter(0.18)
        self.assertIsNone(seg.feed(mouse(1, 0), 0.00))
        self.assertIsNone(seg.feed(mouse(1, 0), 0.05))
        self.assertIsNone(seg.poll(0.20))
        burst = seg.poll(0.30)
        self.assertEqual(len(burst.events), 2)
        self.assertIsNone(seg.poll(1.0))

    def test_real_capture(self):
        with open(FIXTURE, encoding='utf-8') as f:
            sigs = [signature(b.events) for b in bursts(events_from_capture(f))]
        moves = [(s['dx'], s['dy']) for s in sigs if s['kind'] == 'mouse']
        reports = [s['reports'][0] for s in sigs if s['kind'] == 'hid']
        self.assertEqual(set(moves), {(70, 200), (70, 100)})
        self.assertEqual(len(moves), 12)
        self.assertEqual(reports, ['03010000'] + ['03040000'] * 6)


class TableTests(unittest.TestCase):
    def test_classify_after_calibration(self):
        table = build_table({
            'up': [signature([mouse(70, 100)])] * 3,
            'down': [signature([mouse(70, 200)])] * 3,
            'click': [signature([hid('03040000')])] * 3,
        })
        self.assertEqual(len(table['up']), 1)
        self.assertEqual(classify(signature([mouse(-2047, -2047), mouse(72, 98)]), table), 'up')
        self.assertEqual(classify(signature([mouse(70, 200)]), table), 'down')
        self.assertEqual(classify(signature([hid('03040000'), hid('03000000')]), table), 'click')
        self.assertIsNone(classify(signature([hid('03010000')]), table))
        self.assertEqual(classify(signature([mouse(0, 0, 1), mouse(-140, 0), mouse(0, 0, 2)]), table), 'left')

    def test_conflicting_gestures_are_rejected(self):
        with self.assertRaises(ValueError):
            build_table({'up': [signature([mouse(70, 100)])], 'down': [signature([mouse(70, 105)])]})


class HidMouseTests(unittest.TestCase):
    """専用モード: HID レポートのボタン状態から Raw Input と同じイベントを作る。"""

    def test_button_transitions(self):
        self.assertEqual(mouse_event(set(), {1}, 0, 0)['buttons'], 0x01)
        self.assertEqual(mouse_event({1}, {1}, 0, 35)['buttons'], 0)
        self.assertEqual(mouse_event({1}, set(), 0, 0)['buttons'], 0x02)
        self.assertEqual(mouse_event({1}, {2}, 0, 0)['buttons'], 0x02 | 0x04)

    def test_drag_from_hid_reports(self):
        # 位置合わせ → 押下 → 4回移動 → 解放 を HID レポート相当の状態列から作り、ドラッグとして判定できる
        states = [(set(), -2047, -2047), (set(), 105, 100), ({1}, 0, 0)] + [({1}, -35, 0)] * 4 + [(set(), 0, 0)]
        events, previous = [], set()
        for pressed, dx, dy in states:
            events.append(mouse_event(previous, pressed, dx, dy))
            previous = pressed
        self.assertEqual(classify(signature(events), {}), 'left')

    def test_signed(self):
        self.assertEqual(signed(0x801, 12), -2047)
        self.assertEqual(signed(0x7FF, 12), 2047)
        self.assertEqual(signed(0xFFDD, 16), -35)


if __name__ == '__main__':
    unittest.main()
