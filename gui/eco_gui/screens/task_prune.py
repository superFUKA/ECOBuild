"""入力の窓：このPCのタスクブランチだけを消す（ecobuild task prune <番号>）。

タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（新しいタスク：親タスクの番号）

SCREEN = {
    "root": "page",
    "window": {"title": "このPCから片付ける", "width": 560, "height": 320},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "task-form", "props": {"kind": "prune", "issue": {"arg": "issue"}, "text": {"arg": "text"}}},
    ],
    "bindings": [
        {"on": "form.prune", "run": "task prune", "notify": "このPCのタスクブランチを片付けました。", "close": True,
         "args": {"module": {"arg": "module"}, "number": {"payload": "id"}}},
        {"on": "form.cancel", "close": True},
    ],
}
