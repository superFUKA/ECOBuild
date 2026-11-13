"""モジュール › タスク管理 › スプリント：選んだスプリント（選ばなければ今のスプリント）の進み具合と、そのタスク。

上の部分（見出し・表示のタブ・絞り込み）は画面 task-head、表示の部品のつなぎは task-view、右の詳細は task-pane（どの表示でも同じ）。
"""

ARGS = {"module": ".", "filter": {}, "all": False, "ready": False}
# モジュールのフォルダー・開いたときの絞り込み（上の帯が出した値）・読むときの印（閉じたタスクも＝完了か削除を出すとき・着手できるものだけ）

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "スプリント", "width": 1280, "height": 820, "refresh": {"focus": True, "every": 180}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "nav", "screen": "menu", "args": {"current": "board", "module": {"arg": "module"}}},
        {"id": "main", "layout": "column", "look": "tk-page", "children": ["head", "body"]},
        {"id": "head", "screen": "task-head", "args": {"module": {"arg": "module"}, "view": "task-sprint", "scope": "none",
                                                     "filter": {"arg": "filter"}, "all": {"arg": "all"}, "ready": {"arg": "ready"}}},
        # 左に表示、右に選んだタスクの詳細（選ぶまでは出ない。境目は動かせる）
        {"id": "body", "layout": "split", "look": "tk-body", "props": {"direction": "row", "sizes": [None, 380]}, "children": ["view", "pane"]},
        {"id": "view", "layout": "column", "look": "tk-main", "children": ["sprint", "sprint_tasks"]},
        {"id": "sprint", "screen": "task-view", "args": {"module": {"arg": "module"}, "part": "task-sprint", "look": "tk-part", "props": {}}},
        {"id": "sprint_tasks", "screen": "task-view", "args": {"module": {"arg": "module"}, "part": "task-list", "look": "tk-part", "props": {"filtered": False, "empty_text": ""}}},
        {"id": "pane", "screen": "task-pane", "args": {"module": {"arg": "module"}}},
    ],
    "bindings": [
        {"read": "sprint status", "args": {"module": {"arg": "module"}, "name": {"value": "sprint"}}, "to": "sprint.status"},
        {"read": "task list", "args": {"module": {"arg": "module"}, "all": True}, "to": "sprint.tasks"},
        {"on": "sprint.chosen", "set": {"sprint": {"payload": "name"}}},
        {"read": "sprint status", "args": {"module": {"arg": "module"}, "name": {"value": "sprint"}}, "to": "sprint_tasks.tasks", "from": "tasks"},
        {"value": "selected", "to": "sprint_tasks.selected"},
        {"show": "pane", "when": {"detail": "open"}},
    ],
}
