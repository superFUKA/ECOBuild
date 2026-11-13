"""入力の窓：作業を開始・再開する（ecobuild task start <番号> --name <名前> --base <作成元> --account … --no-branch --ignore-blocked --take-over）。

タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（新しいタスク：親タスクの番号）

SCREEN = {
    "root": "page",
    "window": {"title": "作業を開始", "width": 600, "height": 620},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "task-form", "props": {"kind": "start", "issue": {"arg": "issue"}, "text": {"arg": "text"}}},
    ],
    "bindings": [
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "body": True}, "to": "form.status"},
        {"read": "task list", "args": {"module": {"arg": "module"}}, "to": "form.tasks"},
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "form.branches"},
        {"read": "account list", "args": {}, "to": "form.accounts"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "form.account"},
        # 始めたら、その作業空間を（モジュールの窓のタブで）開く（前の GUI と同じ）
        {"on": "form.start", "when": {"no_branch": [None, False]}, "run": "task start", "notify": "作業を開始しました。", "close": True, "after": {"open": "frame-workspace", "args": {"module": {"arg": "module"}, "space": {"result": "workspace"}}},
         "parent": {"selected": {"payload": "id"}, "detail": "open"},  # 始めたタスクを、外の一覧で選ぶ
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "name": {"payload": "name"}, "base": {"payload": "base"}, "account": {"payload": "account"}, "no_branch": {"payload": "no_branch"}, "ignore_blocked": {"payload": "ignore_blocked"}, "take_over": {"payload": "take_over"}}},
        # タスクブランチを作らない：作業空間はないので、一覧のまま
        {"on": "form.start", "when": {"no_branch": True}, "run": "task start", "notify": "作業を開始しました。", "close": True,
         "parent": {"selected": {"payload": "id"}, "detail": "open"},  # 始めたタスクを、外の一覧で選ぶ
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "name": {"payload": "name"}, "base": {"payload": "base"}, "account": {"payload": "account"}, "no_branch": {"payload": "no_branch"}, "ignore_blocked": {"payload": "ignore_blocked"}, "take_over": {"payload": "take_over"}}},
        {"on": "form.cancel", "close": True},
    ],
}
