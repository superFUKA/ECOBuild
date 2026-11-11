"""入力の窓：閉じたタスクのタスクブランチと作業空間を、まとめて消す（ecobuild task prune）。

タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（新しいタスク：親タスクの番号）

SCREEN = {
    "root": "page",
    "window": {"title": "完了したタスクブランチを片付ける", "width": 560, "height": 300},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "task-form", "props": {"kind": "clean", "issue": {"arg": "issue"}, "text": {"arg": "text"}}},
    ],
    "bindings": [
        {"on": "form.clean", "run": "task prune", "notify": "完了したタスクブランチを片付けました。", "close": True, "args": {"module": {"arg": "module"}}},
        {"on": "form.cancel", "close": True},
    ],
}
