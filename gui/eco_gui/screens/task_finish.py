"""入力の窓：提出を取り込む（ecobuild task finish <番号> [--subject …] [--ignore-checks] --complete か --partial）。

タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（新しいタスク：親タスクの番号）

SCREEN = {
    "root": "page",
    "window": {"title": "取り込む", "width": 560, "height": 460},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "task-form", "props": {"kind": "finish", "issue": {"arg": "issue"}, "text": {"arg": "text"}}},
    ],
    "bindings": [
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "body": True}, "to": "form.status"},
        {"on": "form.finish", "run": "task finish", "notify": "取り込みました。", "close": True,
         "args": {"module": {"arg": "module"}, "number": {"payload": "id"}, "subject": {"payload": "subject"}, "ignore_checks": {"payload": "ignore_checks"}, "complete": {"payload": "complete"}, "partial": {"payload": "partial"}}},
        {"on": "form.cancel", "close": True},
    ],
}
