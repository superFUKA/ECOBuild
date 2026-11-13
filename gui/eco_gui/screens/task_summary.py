"""モジュール › タスク管理 › 概要：開いているタスクの数・段階・今のスプリント・自分の次のタスク・期限・マイルストーン・担当者ごとの量・提出・最近の完了。

上の部分（見出し・表示のタブ・絞り込み）は画面 task-head、表示の部品のつなぎは task-view、右の詳細は task-pane（どの表示でも同じ）。
"""

ARGS = {"module": ".", "filter": {}, "all": False, "ready": False}
# モジュールのフォルダー・開いたときの絞り込み（上の帯が出した値）・読むときの印（閉じたタスクも＝完了か削除を出すとき・着手できるものだけ）

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "タスク管理の概要", "width": 1360, "height": 880, "refresh": {"focus": True, "every": 180}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "nav", "screen": "menu", "args": {"current": "board", "module": {"arg": "module"}}},
        {"id": "main", "layout": "column", "look": "tk-page", "children": ["head", "body"]},
        {"id": "head", "screen": "task-head", "args": {"module": {"arg": "module"}, "view": "task-summary", "scope": "none",
                                                     "filter": {"arg": "filter"}, "all": {"arg": "all"}, "ready": {"arg": "ready"}}},
        # 左に表示、右に選んだタスクの詳細（選ぶまでは出ない。境目は動かせる）
        {"id": "body", "layout": "split", "look": "tk-body", "props": {"direction": "row", "sizes": [None, 380]}, "children": ["summary", "pane"]},
        {"id": "summary", "screen": "task-view", "args": {"module": {"arg": "module"}, "part": "task-summary", "props": {}}},
        {"id": "pane", "screen": "task-pane", "args": {"module": {"arg": "module"}}},
    ],
    "bindings": [
        {"read": "task list", "args": {"module": {"arg": "module"}, "all": True}, "to": "summary.tasks"},
        {"read": "sprint status", "args": {"module": {"arg": "module"}}, "to": "summary.sprint"},
        {"read": "task workload", "args": {"module": {"arg": "module"}}, "to": "summary.workload"},
        {"read": "milestone status", "args": {"module": {"arg": "module"}}, "to": "summary.milestones"},
        {"read": "task next", "args": {"module": {"arg": "module"}, "count": 5, "mine": True}, "to": "summary.next"},
        {"read": "task overdue", "args": {"module": {"arg": "module"}, "days": 7}, "to": "summary.overdue"},
        {"read": "task list", "args": {"module": {"arg": "module"}, "to_review": True}, "to": "summary.reviews"},
        {"value": "selected", "to": "summary.selected"},
        # 数のタイル・カードの「開く」・マイルストーン・担当なし：その表示へ（絞り込み付きで）切り替える
        {"on": "summary.go", "open": {"payload": "screen"}, "here": True, "args": {"module": {"arg": "module"}, "filter": {"payload": "filter"}}},
        {"show": "pane", "when": {"detail": "open"}},
    ],
}
