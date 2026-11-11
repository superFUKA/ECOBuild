"""人の画面：その人の担当・作業中・残りの見積もり・期限切れ・提出中の数、作業中・提出・見るように頼まれた提出、担当タスクの表。

タスク管理の画面の中に重ねて開く（担当の丸・名前を押す）。行を選ぶと、そのタスクの詳細を開く。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・（使わない）・アカウント

SCREEN = {
    "root": "page",
    "window": {"title": "担当者", "width": 820, "height": 700},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["person", "list"]},
        {"id": "person", "part": "task-person", "props": {"who": {"arg": "text"}}},
        # 担当タスク：その人のタスクだけ（一覧と同じ表。担当の列は出さない）
        {"id": "list", "part": "task-list", "props": {"assignee": False, "start": {"assignee": {"arg": "text"}}, "empty_text": "ありません"}},
    ],
    "bindings": [
        {"read": "task list", "args": {"module": {"arg": "module"}}, "to": "person.tasks"},
        {"read": "task list", "args": {"module": {"arg": "module"}}, "to": "list.tasks"},
        {"read": "task workload", "args": {"module": {"arg": "module"}}, "to": "person.workload"},
        {"read": "task list", "args": {"module": {"arg": "module"}, "submitted": True}, "to": "person.submitted"},
        {"read": "task list", "args": {"module": {"arg": "module"}, "to_review": True}, "to": "person.reviews"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "person.me", "from": "login"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "list.me", "from": "login"},
        {"read": "sprint list", "args": {"module": {"arg": "module"}}, "to": "list.sprints"},
        {"on": "person.closed", "close": True},
        # タスクを選ぶ：その詳細を、別の窓で開く
        {"on": "person.selected", "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
        {"on": "list.selected", "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
        {"on": "list.edit", "run": "task edit", "notify": "保存しました。",
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "priority": {"payload": "priority"}, "sprint": {"payload": "sprint"},
                  "stage": {"payload": "stage"}, "add_assignee": {"payload": "add_assignee"}, "remove_assignee": {"payload": "remove_assignee"},
                  "clear": {"payload": "clear"}}},
        {"on": "list.close", "run": "task close", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "notify": "完了にしました。"},
        {"on": "list.remove", "run": "task close", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "not_planned": True},
         "notify": "削除しました。"},
        {"on": "list.reopen", "run": "task reopen", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "notify": "開き直しました。"},
        {"on": "list.workspace", "open": "workspace", "args": {"module": {"payload": "path"}}},
    ],
}
