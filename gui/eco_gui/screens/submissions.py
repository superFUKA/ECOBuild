"""モジュール › 提出：見るように頼まれている提出と、提出中のタスク。行から、その提出の窓を開く。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "提出", "width": 900, "height": 680},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "head", "to_review_title", "to_review", "submitted_title", "submitted",
                                                        "revert_title", "revert"]},
        {"id": "nav", "screen": "menu", "args": {"current": "submissions", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "提出", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "to_review_title", "part": "note", "props": {"text": "見るように頼まれている提出"}},
        {"id": "to_review", "part": "table", "props": {
            "columns": [{"key": "number", "label": "#"}, {"key": "title", "label": "題名"}, {"key": "assignees", "label": "担当"},
                        {"key": "branch", "label": "タスクブランチ"}, {"key": "submission.base", "label": "取り込み先"},
                        {"key": "submission.draft", "label": "下書き"}, {"key": "submission.partial", "label": "取り込んだら"}],
            "key": "number", "actions": [{"name": "open", "label": "開く"}],
            "labels": {"submission.draft": {"true": "下書き", "false": ""},
                       "submission.partial": {"true": "タスクを続ける", "false": "タスクを完了する"}},
            "empty_text": "見るように頼まれている提出はありません。",
        }},
        {"id": "submitted_title", "part": "note", "props": {"text": "提出中のタスク"}},
        {"id": "submitted", "part": "table", "props": {
            "columns": [{"key": "number", "label": "#"}, {"key": "title", "label": "題名"}, {"key": "assignees", "label": "担当"},
                        {"key": "branch", "label": "タスクブランチ"}, {"key": "submission.base", "label": "取り込み先"},
                        {"key": "submission.draft", "label": "下書き"}, {"key": "submission.partial", "label": "取り込んだら"}],
            "key": "number", "actions": [{"name": "open", "label": "開く"}],
            "labels": {"submission.draft": {"true": "下書き", "false": ""},
                       "submission.partial": {"true": "タスクを続ける", "false": "タスクを完了する"}},
            "empty_text": "提出中のタスクはありません。",
        }},
        {"id": "revert_title", "part": "note", "props": {"text": "完了したタスクの取り込みを取り消す"}},
        {"id": "revert", "layout": "row", "children": ["revert_task", "do_revert"]},
        {"id": "revert_task", "part": "text-input", "props": {"title": "取り消す、完了したタスクの番号", "placeholder": "例：12"}},
        {"id": "do_revert", "part": "button", "props": {"label": "取り消す", "hint": "取り消しのコミットを持つタスクとタスクブランチを作る"}},
    ],
    "bindings": [
        # 読む（ecobuild task list --to-review・ecobuild task list --submitted）
        {"read": "task list", "args": {"module": {"arg": "module"}, "to_review": True}, "to": "to_review.rows"},
        {"read": "task list", "args": {"module": {"arg": "module"}, "submitted": True}, "to": "submitted.rows"},
        {"on": "reload.pressed", "refresh": True},
        # 提出の窓を開く（タスクごとに1つ。差分・承認・差し戻し・取り下げ・取り込みは、その窓で）
        {"on": "to_review.action", "when": {"action": "open"}, "open": "submission",
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}}},
        {"on": "submitted.action", "when": {"action": "open"}, "open": "submission",
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}}},
        # 取り消す（ecobuild task revert --task <番号>）。番号を入れるまで押せない（省くと「今いるタスクブランチ」に効くため）。
        # 取り消したら、欄は空に戻る
        {"on": "revert_task.changed", "set": {"revert_task": {"payload": "text"}}},
        {"value": "revert_task", "to": "revert_task.text"},
        {"on": "do_revert.pressed", "run": "task revert", "require": ["task"],
         "args": {"module": {"arg": "module"}, "task": {"value": "revert_task"}}, "set": {"revert_task": None}},
    ],
}
