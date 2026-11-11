"""入力の窓：閉じたタスクのタスクブランチと作業空間を、まとめて消す（ecobuild task prune）。

開くと、消すもの・残すものの下見（ecobuild task prune --dry-run）を出す。タスク管理の画面の中に重ねて開く。うまくいったら閉じる。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・（使わない）・（使わない）

SCREEN = {
    "root": "page",
    "window": {"title": "完了したタスクブランチを片付ける", "width": 560, "height": 420},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "task-clean"},
    ],
    "bindings": [
        {"read": "task prune", "preview": True, "args": {"module": {"arg": "module"}}, "to": "form.preview"},
        {"on": "form.clean", "run": "task prune", "notify": "完了したタスクブランチを片付けました。", "close": True, "args": {"module": {"arg": "module"}}},
        {"on": "form.cancel", "close": True},
    ],
}
