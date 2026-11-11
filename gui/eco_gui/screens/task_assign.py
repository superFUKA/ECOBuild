"""入力の窓：担当者を加える（ecobuild task edit <番号> --add-assignee <アカウント>）。

タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（新しいタスク：親タスクの番号）

SCREEN = {
    "root": "page",
    "window": {"title": "担当者を追加", "width": 560, "height": 400},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "task-form", "props": {"kind": "assign", "issue": {"arg": "issue"}, "text": {"arg": "text"}}},
    ],
    "bindings": [
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "body": True}, "to": "form.status"},
        {"read": "task list", "args": {"module": {"arg": "module"}, "all": True}, "to": "form.tasks"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "form.account"},
        {"on": "form.edit", "run": "task edit", "notify": "保存しました。", "close": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "title": {"payload": "title"}, "body": {"payload": "body"}, "parent": {"payload": "parent"}, "clear_parent": {"payload": "clear_parent"}, "add_blocked_by": {"payload": "add_blocked_by"}, "remove_blocked_by": {"payload": "remove_blocked_by"},
                  "add_assignee": {"payload": "add_assignee"}, "add_label": {"payload": "add_label"}}},
        {"on": "form.cancel", "close": True},
    ],
}
