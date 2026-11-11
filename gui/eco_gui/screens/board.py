"""モジュール › タスク管理 › ボード：タスクを段階ごとの列に並べる。カードを別の列へ落として、段階を変える・始める・完了にする。

上の帯（表示のタブと絞り込み）・右の詳細は、タスク管理のどの表示でも同じ（tasks・board・schedule・task-next・task-sprint・task-summary）。
絞り込みは画面の引数で受け、表示を切り替えるときに次の画面へ渡す。
"""

ARGS = {"module": ".", "search": "", "assignee": "", "sprint": "", "milestone": "", "ready": False, "closed": False, "deleted": False,
        "all": False}  # モジュールのフォルダーと、絞り込み（all：閉じたタスクも読む＝完了か削除を出すとき）

SCREEN = {
    "root": "page",
    "window": {"title": "ボード", "width": 1280, "height": 820, "refresh": {"focus": True, "every": 180}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "tk-page", "children": ["top", "bar", "body"]},
        {"id": "nav", "screen": "menu", "args": {"current": "board", "module": {"arg": "module"}}},
        {"id": "top", "layout": "row", "look": "tk-top", "children": ["title", "reload", "new"]},
        {"id": "title", "part": "note", "props": {"text": "タスク管理", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "更新"}},
        {"id": "new", "part": "button", "props": {"label": "＋ 新しいタスク", "primary": True}},
        {"id": "bar", "part": "task-bar", "props": {"view": "board", "scope": "all", "start": {
            "search": {"arg": "search"}, "assignee": {"arg": "assignee"}, "sprint": {"arg": "sprint"}, "milestone": {"arg": "milestone"},
            "ready": {"arg": "ready"}, "closed": {"arg": "closed"}, "deleted": {"arg": "deleted"}}}},
        # 左に表示、右に選んだタスクの詳細（選ぶまでは出ない。境目は動かせる）
        {"id": "body", "layout": "split", "look": "tk-body", "props": {"direction": "row", "sizes": [None, 380]}, "children": ["board", "pane"]},
        {"id": "board", "part": "board", "look": "tk-main", "props": {"start": {
            "search": {"arg": "search"}, "assignee": {"arg": "assignee"}, "sprint": {"arg": "sprint"}, "milestone": {"arg": "milestone"},
            "ready": {"arg": "ready"}, "closed": {"arg": "closed"}, "deleted": {"arg": "deleted"}}}},
        {"id": "pane", "screen": "task-pane", "args": {"module": {"arg": "module"}}},
    ],
    "bindings": [
        {"read": "task list", "args": {"module": {"arg": "module"}, "all": {"arg": "all"}, "ready": {"arg": "ready"}}, "to": "bar.tasks"},
        {"read": "sprint list", "args": {"module": {"arg": "module"}}, "to": "bar.sprints"},
        {"read": "milestone list", "args": {"module": {"arg": "module"}}, "to": "bar.milestones"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "bar.me", "from": "login"},
        {"read": "task list", "args": {"module": {"arg": "module"}, "all": {"arg": "all"}, "ready": {"arg": "ready"}}, "to": "board.tasks"},
        # 完了の列：最近完了したもの（閉じたタスクも読む）
        {"read": "task list", "args": {"module": {"arg": "module"}, "all": True}, "to": "board.recent"},
        {"read": "sprint list", "args": {"module": {"arg": "module"}}, "to": "board.sprints"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "board.me", "from": "login"},
        {"value": "filter", "to": "board.filter"},
        {"value": "selected", "to": "board.selected"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "new.pressed", "open": "task-new", "args": {"module": {"arg": "module"}}, "inside": True},
        # 上の帯：表示を切り替える（絞り込みを持って行く）・絞り込む（見せ方だけ）・読み直しの要る印は、この画面を開き直す
        {"on": "bar.view", "open": {"payload": "id"}, "here": True,
         "args": {"module": {"arg": "module"},
                  "search": {"payload": "search"}, "assignee": {"payload": "assignee"}, "sprint": {"payload": "sprint"}, "milestone": {"payload": "milestone"},
                  "ready": {"payload": "ready"}, "closed": {"payload": "closed"}, "deleted": {"payload": "deleted"}, "all": {"payload": "all"}}},
        {"on": "bar.changed", "set": {"filter": {"payload": ""}}},
        {"on": "bar.reload", "open": "board", "here": True,
         "args": {"module": {"arg": "module"},
                  "search": {"payload": "search"}, "assignee": {"payload": "assignee"}, "sprint": {"payload": "sprint"}, "milestone": {"payload": "milestone"},
                  "ready": {"payload": "ready"}, "closed": {"payload": "closed"}, "deleted": {"payload": "deleted"}, "all": {"payload": "all"}}},
        {"show": "pane", "when": {"detail": "open"}},
        # board：選ぶと右に詳細、入力の窓は中に重ねて開く、その場の変更は task edit
        {"on": "board.selected", "set": {"selected": {"payload": "id"}, "detail": "open"}},
        {"on": "board.dialog", "open": {"payload": "screen"}, "inside": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "text": {"payload": "text"}}},
        {"on": "board.edit", "run": "task edit", "notify": "保存しました。",
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"},
                  "priority": {"payload": "priority"}, "sprint": {"payload": "sprint"}, "stage": {"payload": "stage"}, "estimate": {"payload": "estimate"},
                  "due": {"payload": "due"}, "planned_start": {"payload": "planned_start"}, "planned_end": {"payload": "planned_end"}, "milestone": {"payload": "milestone"},
                  "clear_milestone": {"payload": "clear_milestone"}, "add_assignee": {"payload": "add_assignee"}, "remove_assignee": {"payload": "remove_assignee"}, "add_label": {"payload": "add_label"},
                  "remove_label": {"payload": "remove_label"}, "clear": {"payload": "clear"}}},
        {"on": "board.close", "run": "task close", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "notify": "完了にしました。"},
        {"on": "board.remove", "run": "task close", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "not_planned": True}, "notify": "削除しました。"},
        {"on": "board.reopen", "run": "task reopen", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "notify": "開き直しました。"},
        {"on": "board.workspace", "open": "workspace", "args": {"module": {"payload": "path"}}},
    ],
}
