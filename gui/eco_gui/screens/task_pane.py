"""タスクの詳細（タスク管理の表示の右に置く。選んだタスク＝共有の値 selected）。

その場で変える（task edit）・コメント（task comment）・開き直す・完了にする・削除・提出の取り下げ・手元で確認・取り込みの取り消し。
欄の多い操作（開始・編集・完了・作業を捨てる ほか）は、入力の窓（task-start ほか）を中に重ねて開く。
"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "detail",
    "nodes": [
        {"id": "detail", "part": "task-detail", "look": "tk-detail"},
    ],
    "bindings": [
        {"value": "selected", "to": "detail.number"},
        {"on": "detail.closed", "set": {"selected": None, "detail": None}},
        # 読む：タスクの状態と、その場の欄の選択肢
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"value": "selected"}, "body": True}, "require": ["number"], "to": "detail.status"},
        {"read": "sprint list", "args": {"module": {"arg": "module"}}, "to": "detail.sprints"},
        {"read": "milestone list", "args": {"module": {"arg": "module"}}, "to": "detail.milestones"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "detail.account"},
        {"on": "detail.selected", "set": {"selected": {"payload": "id"}, "detail": "open"}},  # つながりのタスクへ
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
