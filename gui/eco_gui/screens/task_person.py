"""人の画面：その人の担当・作業中・残りの見積もり・期限切れ・提出中の数、作業中・提出・見るように頼まれた提出、担当タスクの表。

タスク管理の画面の中に重ねて開く（担当の丸・名前を押す）。行を選ぶと、そのタスクの詳細を別の窓で開く。
担当タスクの表のつなぎ（右クリックのメニュー・入力の窓）は、一覧と同じ（task-view）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・（使わない）・アカウント

SCREEN = {
    "root": "page",
    "window": {"title": "担当者", "width": 820, "height": 700},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["person", "list"]},
        {"id": "person", "part": "task-person", "props": {"who": {"arg": "text"}}},
        # 担当タスク：その人のタスクだけ（一覧と同じ表。担当の列は出さない）
        {"id": "list", "screen": "task-view", "args": {"module": {"arg": "module"}, "part": "task-list", "look": "tk-part", "props": {
            "assignee": False, "start": {"assignee": {"arg": "text"}}, "empty_text": "ありません"}}},
    ],
    "bindings": [
        {"read": "task list", "args": {"module": {"arg": "module"}}, "to": "person.tasks"},
        {"read": "task list", "args": {"module": {"arg": "module"}}, "to": "list.tasks"},
        {"read": "task workload", "args": {"module": {"arg": "module"}}, "to": "person.workload"},
        {"read": "task list", "args": {"module": {"arg": "module"}, "submitted": True}, "to": "person.submitted"},
        {"read": "task list", "args": {"module": {"arg": "module"}, "to_review": True}, "to": "person.reviews"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "person.me", "from": "login"},
        {"on": "person.closed", "close": True},
        # タスクを選ぶ：その詳細を、別の窓で開く
        {"on": "person.selected", "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
        {"on": "list.selected", "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
    ],
}
