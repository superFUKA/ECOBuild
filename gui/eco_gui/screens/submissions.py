"""モジュール › 提出：届いている提出を、届け先のブランチごとに。行を選ぶと、その提出の詳細がこの窓の中に開く。

タスクの提出（task list --submitted）と、ブランチ同士の提出（branch list の submission）を1つの一覧にする。
"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "提出", "width": 1280, "height": 820, "refresh": {"focus": True, "every": 180}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "section", "list", "revert_box"]},
        {"id": "section", "screen": "branch-tabs", "args": {"current": "submissions", "module": {"arg": "module"}}},
        {"id": "nav", "screen": "menu", "args": {"current": "branches", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "ブランチ", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "list", "part": "review-submissions"},
        # 完了したタスクの取り込みを取り消す
        {"id": "revert_box", "layout": "column", "look": "card", "children": ["revert_title", "revert"]},
        {"id": "revert_title", "part": "note", "props": {"text": "完了したタスクの取り込みを取り消す"}},
        {"id": "revert", "layout": "row", "children": ["revert_task", "do_revert"]},
        {"id": "revert_task", "part": "text-input", "props": {"title": "取り消す、完了したタスクの番号", "placeholder": "例：12"}},
        {"id": "do_revert", "part": "button", "props": {"label": "取り消す", "hint": "取り消しのコミットを持つタスクとタスクブランチを作る"}},
    ],
    "bindings": [
        # 読む（ecobuild task list --submitted・--to-review、branch list、account show）
        {"read": "task list", "args": {"module": {"arg": "module"}, "submitted": True}, "to": "list.tasks"},
        {"read": "task list", "args": {"module": {"arg": "module"}, "to_review": True}, "to": "list.to_review"},
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "list.branches"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "list.access"},
        {"on": "reload.pressed", "refresh": True},
        # 選んだ提出の詳細を、この窓の中に開く（差分・承認・差し戻し・取り下げ・取り込みは、その中で）
        {"on": "list.selected", "when": {"kind": "task"}, "open": "submission", "inside": True,
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}}},
        {"on": "list.selected", "when": {"kind": "branch"}, "open": "review-branch", "inside": True,
         "args": {"module": {"arg": "module"}, "branch": {"payload": "id"}}},
        # 取り消す（ecobuild task revert --task <番号>）。番号を入れるまで押せない（省くと「今いるタスクブランチ」に効くため）。
        # 取り消したら、欄は空に戻る
        {"on": "revert_task.changed", "set": {"revert_task": {"payload": "text"}}},
        {"value": "revert_task", "to": "revert_task.text"},
        {"on": "do_revert.pressed", "run": "task revert", "require": ["task"],
         "args": {"module": {"arg": "module"}, "task": {"value": "revert_task"}}, "set": {"revert_task": None},
         "notify": "取り込みを取り消すタスクを作りました。"},
    ],
}
