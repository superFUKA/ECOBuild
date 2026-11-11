"""入力の窓：作業を取り込まずに捨てる（ecobuild task drop <番号> [--close]）。

タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（新しいタスク：親タスクの番号）

SCREEN = {
    "root": "page",
    "window": {"title": "作業を捨てる", "width": 560, "height": 340},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "task-form", "props": {"kind": "drop", "issue": {"arg": "issue"}, "text": {"arg": "text"}}},
    ],
    "bindings": [
        {"on": "form.drop", "run": "task drop", "notify": "作業を捨てました。", "close": True,
         "args": {"module": {"arg": "module"}, "number": {"payload": "id"}, "close": {"payload": "close"}}},
        {"on": "form.cancel", "close": True},
    ],
}
