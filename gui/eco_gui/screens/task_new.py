"""入力の窓：新しいタスクを作る（ecobuild task new <題名> --body … --assignee … --priority … ほか。「作ったら始める」は --start --name <名前>）。

タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（新しいタスク：親タスクの番号）

SCREEN = {
    "root": "page",
    "window": {"title": "新しいタスク", "width": 620, "height": 780},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "task-form", "props": {"kind": "new", "issue": {"arg": "issue"}, "text": {"arg": "text"}}},
    ],
    "bindings": [
        {"read": "task list", "args": {"module": {"arg": "module"}}, "to": "form.tasks"},
        {"read": "sprint list", "args": {"module": {"arg": "module"}}, "to": "form.sprints"},
        {"read": "milestone list", "args": {"module": {"arg": "module"}}, "to": "form.milestones"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "form.account"},
        # GitHub のメンバー（担当者の候補に足す。届くのを待たずに窓を出す）
        {"read": "module members", "args": {"module": {"arg": "module"}}, "lazy": True, "to": "form.members"},
        {"on": "form.new", "run": "task new", "notify": "タスク #{task.number} を作成しました。", "close": True,
         "parent": {"selected": {"result": "task.number"}, "detail": "open"},  # 作ったタスクを、外の一覧で選ぶ（右に詳細が出る）
         "args": {"module": {"arg": "module"}, "title": {"payload": "title"}, "body": {"payload": "body"}, "stage": {"payload": "stage"}, "assignee": {"payload": "assignee"}, "priority": {"payload": "priority"}, "estimate": {"payload": "estimate"}, "sprint": {"payload": "sprint"}, "planned_start": {"payload": "planned_start"}, "planned_end": {"payload": "planned_end"}, "due": {"payload": "due"},
                  "label": {"payload": "label"}, "milestone": {"payload": "milestone"}, "parent": {"payload": "parent"}, "blocked_by": {"payload": "blocked_by"}, "start": {"payload": "start"}, "name": {"payload": "name"}}},
        {"on": "form.cancel", "close": True},
    ],
}
