"""モジュール › タスク管理 › 一覧：タスクの表（並べ替え・絞り込み）と、右に選んだタスクの詳細。

上の部分（見出し・表示のタブ・絞り込み）は画面 task-head、表示の部品のつなぎは task-view、右の詳細は task-pane（どの表示でも同じ）。
"""

ARGS = {"module": ".", "filter": {}, "all": False, "ready": False}
# モジュールのフォルダー・開いたときの絞り込み（上の帯が出した値）・読むときの印（閉じたタスクも＝完了か削除を出すとき・着手できるものだけ）

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "タスク", "width": 1360, "height": 880, "refresh": {"focus": True, "every": 180}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "nav", "screen": "menu", "args": {"current": "board", "module": {"arg": "module"}}},
        {"id": "main", "layout": "column", "look": "tk-page", "children": ["head", "body"]},
        {"id": "head", "screen": "task-head", "args": {"module": {"arg": "module"}, "view": "tasks", "scope": "all",
                                                     "filter": {"arg": "filter"}, "all": {"arg": "all"}, "ready": {"arg": "ready"}}},
        # 左に表示、右に選んだタスクの詳細（選ぶまでは出ない。境目は動かせる）
        {"id": "body", "layout": "split", "look": "tk-body", "props": {"direction": "row", "sizes": [None, 380]}, "children": ["list", "pane"]},
        {"id": "list", "screen": "task-view", "args": {"module": {"arg": "module"}, "part": "task-list", "props": {"foot": True, "start": {"arg": "filter"}}}},
        {"id": "pane", "screen": "task-pane", "args": {"module": {"arg": "module"}}},
    ],
    "bindings": [
        {"read": "task list", "args": {"module": {"arg": "module"}, "all": {"arg": "all"}, "ready": {"arg": "ready"}}, "to": "list.tasks"},
        {"value": "filter", "to": "list.filter"},
        {"value": "selected", "to": "list.selected"},
        {"show": "pane", "when": {"detail": "open"}},
    ],
}
