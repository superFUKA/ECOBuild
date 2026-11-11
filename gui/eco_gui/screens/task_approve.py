"""入力の窓：提出を承認して取り込む（ecobuild task approve <番号> [--message …]）。

タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（新しいタスク：親タスクの番号）

SCREEN = {
    "root": "page",
    "window": {"title": "承認して取り込む", "width": 560, "height": 400},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "task-form", "props": {"kind": "approve", "issue": {"arg": "issue"}, "text": {"arg": "text"}}},
    ],
    "bindings": [
        {"on": "form.approve", "run": "task approve", "notify": "承認して取り込みました。", "close": True,
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}, "message": {"payload": "message"}}},
        {"on": "form.cancel", "close": True},
    ],
}
