"""モジュール › タスク管理 › タスクの詳細（1つのタスクを、窓いっぱいに）。中身は、一覧の右に出す詳細（task-pane）と同じ。"""

ARGS = {"module": ".", "issue": 0}  # モジュールのフォルダーと、タスクの番号

SCREEN = {
    "root": "page",
    "window": {"title": "タスクの詳細", "width": 1280, "height": 820, "refresh": {"focus": True, "every": 180}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "tk-page", "children": ["top", "scroll"]},
        {"id": "nav", "screen": "menu", "args": {"current": "tasks", "module": {"arg": "module"}}},
        {"id": "top", "layout": "row", "look": "tk-top", "children": ["title", "back", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "タスク管理", "heading": True}},
        {"id": "back", "part": "button", "props": {"label": "‹ 一覧へ"}},
        {"id": "reload", "part": "button", "props": {"label": "更新"}},
        {"id": "scroll", "layout": "column", "look": "tk-single", "children": ["detail"]},
        {"id": "detail", "part": "task-detail", "props": {"closable": False}},
    ],
    "bindings": [
        {"on": "reload.pressed", "refresh": True},
        {"on": "back.pressed", "open": "tasks", "args": {"module": {"arg": "module"}}, "here": True},
        # 読む：タスクの状態と、その場の欄の選択肢
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "body": True}, "require": ["number"], "to": "detail.status"},
        {"read": "sprint list", "args": {"module": {"arg": "module"}}, "to": "detail.sprints"},
        {"read": "milestone list", "args": {"module": {"arg": "module"}}, "to": "detail.milestones"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "detail.account"},
        {"on": "detail.selected", "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "here": True},  # つながりのタスクへ
        {"on": "detail.dialog", "open": {"payload": "screen"}, "inside": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "text": {"payload": "text"}}},
        # その場で変える（ecobuild task edit <番号> --priority … ほか。入れた値だけが渡る）
        {"on": "detail.edit", "run": "task edit", "notify": "保存しました。",
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"},
                  "priority": {"payload": "priority"}, "sprint": {"payload": "sprint"}, "stage": {"payload": "stage"}, "estimate": {"payload": "estimate"},
                  "due": {"payload": "due"}, "planned_start": {"payload": "planned_start"}, "planned_end": {"payload": "planned_end"}, "milestone": {"payload": "milestone"},
                  "clear_milestone": {"payload": "clear_milestone"}, "add_assignee": {"payload": "add_assignee"}, "remove_assignee": {"payload": "remove_assignee"}, "add_label": {"payload": "add_label"},
                  "remove_label": {"payload": "remove_label"}, "clear": {"payload": "clear"}}},
        {"on": "detail.close", "run": "task close", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "notify": "完了にしました。"},
        {"on": "detail.remove", "run": "task close", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "not_planned": True}, "notify": "削除しました。"},
        {"on": "detail.reopen", "run": "task reopen", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "notify": "開き直しました。"},
        {"on": "detail.workspace", "open": "workspace", "args": {"module": {"payload": "path"}}},
        {"on": "detail.comment", "run": "task comment", "notify": "コメントしました。",
         "args": {"module": {"arg": "module"}, "number": {"payload": "id"}, "message": {"payload": "message"}}},
        # 提出：取り下げる（確かめてから）・手元で確認・取り込みを取り消す（確かめてから）。差分は提出の画面で
        {"on": "detail.withdraw", "run": "task withdraw", "args": {"module": {"arg": "module"}, "number": {"payload": "id"}}, "notify": "提出を取り下げました。"},
        {"on": "detail.review", "run": "task review", "args": {"module": {"arg": "module"}, "number": {"payload": "id"}}, "notify": "提出を、確認用の作業空間に取り出しました。"},
        {"on": "detail.revert", "run": "task revert", "args": {"module": {"arg": "module"}, "number": {"payload": "id"}}, "notify": "取り込みを取り消すタスクを作りました。"},
        {"on": "detail.submission", "open": "submission", "args": {"module": {"arg": "module"}, "task": {"payload": "id"}}, "here": True},
    ],
}
