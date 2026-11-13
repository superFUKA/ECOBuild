"""モジュール › 提出：届いている提出を、届け先のブランチごとに。左の一覧で選んだ提出の詳細を、右に出す。

タスクの提出（task list --submitted）と、ブランチ同士の提出（branch list の submission）を1つの一覧にする。
初めは先頭の提出を選ぶ。↑↓ で選び直すと、右の詳細も替わる。行の右クリックで、詳細のボタンと同じ操作ができる。
"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "提出", "width": 1280, "height": 820, "refresh": {"focus": True, "every": 180}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "section", "body", "revert_box"]},
        {"id": "section", "screen": "branch-tabs", "args": {"current": "submissions", "module": {"arg": "module"}}},
        {"id": "nav", "screen": "menu", "args": {"current": "branches", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "ブランチ", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        # 左に一覧、右に選んだ提出の詳細（境目は動かせる）
        {"id": "body", "layout": "split", "props": {"direction": "row", "sizes": [420, None]}, "children": ["list", "detail"]},
        {"id": "list", "part": "review-submissions"},
        {"id": "detail", "part": "review-submission"},
        # 完了したタスクの取り込みを取り消す
        {"id": "revert_box", "layout": "column", "look": "card", "children": ["revert_title", "revert"]},
        {"id": "revert_title", "part": "note", "props": {"text": "完了したタスクの取り込みを取り消す"}},
        {"id": "revert", "layout": "row", "children": ["revert_task", "do_revert"]},
        {"id": "revert_task", "part": "text-input", "props": {"title": "取り消す、完了したタスクの番号", "placeholder": "例：12"}},
        {"id": "do_revert", "part": "button", "props": {"label": "取り消す", "hint": "取り消しのコミットを持つタスクとタスクブランチを作る"}},
    ],
    "bindings": [
        # 読む（ecobuild task list --submitted・--to-review、branch list、account show、module show）
        {"read": "task list", "args": {"module": {"arg": "module"}, "submitted": True}, "to": "list.tasks"},
        {"read": "task list", "args": {"module": {"arg": "module"}, "to_review": True}, "to": "list.to_review"},
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "list.branches"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "list.access"},
        {"on": "reload.pressed", "refresh": True},
        # 選ぶ：タスクの提出か、ブランチ同士の提出か（片方は空）。右の詳細は、選んだものを読む
        {"on": "list.selected", "set": {"sub_task": {"payload": "task"}, "sub_branch": {"payload": "branch"}, "sub_open": "open"}},
        {"value": "sub_task", "to": "list.selected_task"},
        {"value": "sub_branch", "to": "list.selected_branch"},
        {"show": "detail", "when": {"sub_open": "open"}},
        {"read": "task status", "args": {"module": {"arg": "module"}, "issue": {"value": "sub_task"}}, "require": ["issue"], "to": "detail.task"},
        {"value": "sub_branch", "to": "detail.name"},
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "detail.branches"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "detail.access"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "detail.spaces", "from": "workspaces"},
        # 詳細のボタンと、一覧の行の右クリック（同じ操作）
        {"on": "detail.action", "when": {"action": "refresh"}, "refresh": True},
        {"on": "detail.action", "when": {"action": "diff"}, "run": "task diff", "args": {"module": {"arg": "module"}, "task": {"payload": "id"}, "gui": True},
         "instead": {"when": {"code": "tool_missing"}, "open": "review-diff", "args": {"module": {"arg": "module"}, "task": {"payload": "id"}}, "inside": True}},
        {"on": "list.action", "when": {"action": "diff"}, "run": "task diff", "args": {"module": {"arg": "module"}, "task": {"payload": "id"}, "gui": True},
         "instead": {"when": {"code": "tool_missing"}, "open": "review-diff", "args": {"module": {"arg": "module"}, "task": {"payload": "id"}}, "inside": True}},
        # タスク：この窓のタスク管理で、そのタスクを選んで右に詳細
        {"on": "detail.action", "when": {"action": "task"}, "open": "tasks", "args": {"module": {"arg": "module"}, "pick": {"payload": "id"}}},
        {"on": "list.action", "when": {"action": "task"}, "open": "tasks", "args": {"module": {"arg": "module"}, "pick": {"payload": "id"}}},
        {"on": "detail.action", "when": {"action": "open_review"}, "open": "frame-workspace",
         "args": {"module": {"arg": "module"}, "space": {"payload": "workspace"}}},
        # 手元で確認（ecobuild task review --task <番号> [--done]）・取り下げ（ecobuild task withdraw --task <番号>。確かめてから）
        {"on": "detail.action", "when": {"action": "review"}, "run": "task review", "after": {"open": "frame-workspace", "args": {"module": {"arg": "module"}, "space": {"result": "workspace"}}},
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}},
         "notify": "提出を、確認用の作業空間に取り出しました。そこでビルド・テスト・実行して確かめ、ここで承認か差し戻しをします。"},
        {"on": "list.action", "when": {"action": "review"}, "run": "task review", "after": {"open": "frame-workspace", "args": {"module": {"arg": "module"}, "space": {"result": "workspace"}}},
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}},
         "notify": "提出を、確認用の作業空間に取り出しました。そこでビルド・テスト・実行して確かめ、ここで承認か差し戻しをします。"},
        {"on": "detail.action", "when": {"action": "review_done"}, "run": "task review",
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}, "done": True}, "notify": "確認を終え、確認用の作業空間を消しました。"},
        {"on": "detail.action", "when": {"action": "withdraw"}, "run": "task withdraw",
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}}, "notify": "提出を取り下げました。"},
        {"on": "list.action", "when": {"action": "withdraw"}, "run": "task withdraw",
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}}, "notify": "提出を取り下げました。"},
        # 入力の要る操作：入力の窓を重ねて開く（何が起きるかの表つき）
        {"on": "detail.action", "when": {"action": "comment"}, "open": "task-comment", "inside": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
        {"on": "list.action", "when": {"action": "comment"}, "open": "task-comment", "inside": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
        {"on": "detail.action", "when": {"action": "reject"}, "open": "task-reject", "inside": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
        {"on": "list.action", "when": {"action": "reject"}, "open": "task-reject", "inside": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
        {"on": "detail.action", "when": {"action": "approve"}, "open": "task-approve", "inside": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
        {"on": "list.action", "when": {"action": "approve"}, "open": "task-approve", "inside": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
        {"on": "detail.action", "when": {"action": "finish"}, "open": "task-finish", "inside": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
        {"on": "list.action", "when": {"action": "finish"}, "open": "task-finish", "inside": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
        {"on": "detail.action", "when": {"action": "apply"}, "open": "task-apply", "inside": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
        # ブランチ同士の提出を取り込む：入力の窓（CI が失敗していても取り込むか）
        {"on": "detail.action", "when": {"action": "merge"}, "open": "review-merge", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"payload": "id"}}},
        {"on": "list.action", "when": {"action": "merge"}, "open": "review-merge", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"payload": "id"}}},
        # 取り消す（ecobuild task revert --task <番号>）。番号を入れるまで押せない（省くと「今いるタスクブランチ」に効くため）。
        # 取り消したら、欄は空に戻る
        {"on": "revert_task.changed", "set": {"revert_task": {"payload": "text"}}},
        {"value": "revert_task", "to": "revert_task.text"},
        {"on": "do_revert.pressed", "run": "task revert", "require": ["task"],
         "args": {"module": {"arg": "module"}, "task": {"value": "revert_task"}}, "set": {"revert_task": None},
         "notify": "取り込みを取り消すタスクを作りました。",
         # 取り消しが衝突で止まった：止まっている作業空間を開く（衝突の帯で、直して「続ける」と案内する）
         "instead": {"when": {"code": "merge_conflict"}, "open": "frame-workspace",
                     "args": {"module": {"arg": "module"}, "space": {"error": "details.workspace"}}}},
    ],
}
