"""モジュール › タスク管理 › ボード：タスクを段階ごとの列に並べる。カードを別の列へ落として、段階を変える・始める・完了にする。

上の部分（見出し・表示のタブ・絞り込み）は画面 task-head、表示の部品のつなぎは task-view、右の詳細は task-pane（どの表示でも同じ）。
"""

ARGS = {"module": ".", "filter": {}, "all": False, "ready": False}
# モジュールのフォルダー・開いたときの絞り込み（上の帯が出した値）・読むときの印（閉じたタスクも＝完了か削除を出すとき・着手できるものだけ）

SCREEN = {
    "root": "page",
    "window": {"title": "ボード", "width": 1280, "height": 820, "refresh": {"focus": True, "every": 180}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "nav", "screen": "menu", "args": {"current": "tasks", "module": {"arg": "module"}}},
        {"id": "main", "layout": "column", "look": "tk-page", "children": ["head", "body"]},
        {"id": "head", "screen": "task-head", "args": {"module": {"arg": "module"}, "view": "board", "scope": "all",
                                                     "filter": {"arg": "filter"}, "all": {"arg": "all"}, "ready": {"arg": "ready"}}},
        # 左に表示、右に選んだタスクの詳細（選ぶまでは出ない。境目は動かせる）
        {"id": "body", "layout": "split", "look": "tk-body", "props": {"direction": "row", "sizes": [None, 380]}, "children": ["board", "pane"]},
        {"id": "board", "screen": "task-view", "args": {"module": {"arg": "module"}, "part": "board", "props": {"start": {"arg": "filter"}}}},
        {"id": "pane", "screen": "task-pane", "args": {"module": {"arg": "module"}}},
    ],
    "bindings": [
        {"read": "task list", "args": {"module": {"arg": "module"}, "all": {"arg": "all"}, "ready": {"arg": "ready"}}, "to": "board.tasks"},
        # 完了の列：最近完了したもの（閉じたタスクも読む）
        {"read": "task list", "args": {"module": {"arg": "module"}, "all": True}, "to": "board.recent"},
        {"value": "filter", "to": "board.filter"},
        {"value": "selected", "to": "board.selected"},
        {"show": "pane", "when": {"detail": "open"}},
    ],
}
