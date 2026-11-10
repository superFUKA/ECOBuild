"""モジュール › タスク：開いているタスクの一覧。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "タスク", "width": 760, "height": 560},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "head", "tasks", "start_name", "form"]},
        {"id": "nav", "screen": "menu", "args": {"current": "tasks", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "タスク", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "tasks", "part": "table", "props": {
            "columns": [{"key": "number", "label": "#"}, {"key": "title", "label": "題名"}, {"key": "stage", "label": "段階"},
                        {"key": "assignees", "label": "担当"}],
            "key": "number",
            "actions": [{"name": "open", "label": "詳細"}, {"name": "start", "label": "始める"}, {"name": "close", "label": "閉じる"}],
            "labels": {"stage": {"planned": "計画中", "todo": "未着手", "in_progress": "作業中", "in_review": "レビュー待ち", "done": "完了"}},
            "empty_text": "開いているタスクはありません。",
        }},
        {"id": "start_name", "part": "text-input", "props": {"title": "「始める」で作るタスクブランチの名前", "placeholder": "例：ログイン画面"}},
        {"id": "form", "layout": "row", "children": ["new_title", "new"]},
        {"id": "new_title", "part": "text-input", "props": {"title": "新しいタスクの題名", "placeholder": "何をするか"}},
        {"id": "new", "part": "button", "props": {"label": "＋ 作る", "primary": True}},
    ],
    "bindings": [
        {"read": "task list", "args": {"module": {"arg": "module"}}, "to": "tasks.rows"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "new_title.changed", "set": {"new_title": {"payload": "text"}}},
        {"value": "new_title", "to": "new_title.text"},  # 作ったら、欄は空に戻る
        {"on": "new.pressed", "run": "task new", "args": {"module": {"arg": "module"}, "title": {"value": "new_title"}},
         "set": {"new_title": None}},
        {"on": "start_name.changed", "set": {"start_name": {"payload": "text"}}},
        {"value": "start_name", "to": "start_name.text"},
        # 行の「詳細」：同じ窓で、そのタスクの詳細に切り替える
        {"on": "tasks.action", "when": {"action": "open"}, "open": "task",
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "here": True},
        # 行のボタン（ecobuild task start <番号> --name <名前>・ecobuild task close <番号>）
        {"on": "tasks.action", "when": {"action": "start"}, "run": "task start",
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "name": {"value": "start_name"}}, "set": {"start_name": None}},
        {"on": "tasks.action", "when": {"action": "close"}, "run": "task close", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
    ],
}
