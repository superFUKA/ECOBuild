"""入力の窓：題名・本文・親タスク・先に終わるべきタスクを変える（ecobuild task edit <番号> --title … --body … --parent … ほか）。

タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（新しいタスク：親タスクの番号）

SCREEN = {
    "root": "page",
    "window": {"title": "タスクを編集", "width": 620, "height": 660},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "task-form", "props": {"kind": "edit", "issue": {"arg": "issue"}, "text": {"arg": "text"}}},
    ],
    "bindings": [
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "body": True}, "to": "form.status"},
        {"read": "task list", "args": {"module": {"arg": "module"}}, "to": "form.tasks"},
        {"on": "form.edit", "run": "task edit", "notify": "保存しました。", "close": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "title": {"payload": "title"}, "body": {"payload": "body"}, "parent": {"payload": "parent"}, "clear_parent": {"payload": "clear_parent"}, "add_blocked_by": {"payload": "add_blocked_by"}, "remove_blocked_by": {"payload": "remove_blocked_by"},
                  "add_assignee": {"payload": "add_assignee"}, "add_label": {"payload": "add_label"}}},
        {"on": "form.cancel", "close": True},
    ],
}
