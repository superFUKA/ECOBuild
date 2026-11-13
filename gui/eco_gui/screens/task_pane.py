"""タスクの詳細（部品 task-detail と、そのつなぎ）。タスク管理の表示の右に置く・窓いっぱいに出す（画面 task）。

どのタスクを出すかは引数 number：一覧で選んだもの（共有の値 selected。既定）か、決まった番号。
その場で変える・完了・削除・開き直す・入力の窓は、タスクを描くほかの部品と同じ（task-view）。ここで足すのは、コメント（task comment）、
提出の取り下げ・手元で確認・取り込みの取り消し、差分（提出の画面）、提出のボタンの灰色と理由（task approve・reject・finish の --can）。
"""

ARGS = {"module": ".", "number": {"value": "selected"}, "look": "tk-detail", "closable": True}
# モジュールのフォルダー・出すタスクの番号（共有の値への参照か、番号）・見た目の名前・× で閉じられるか

SCREEN = {
    "root": "detail",
    "nodes": [
        {"id": "detail", "screen": "task-view", "args": {"module": {"arg": "module"}, "part": "task-detail", "look": {"arg": "look"},
                                                         "props": {"closable": {"arg": "closable"}}}},
    ],
    "bindings": [
        {"value": "selected", "to": "detail.number"},
        {"on": "detail.closed", "set": {"selected": None, "detail": None}},
        # 読む：タスクの状態と、その場の欄の選択肢
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "number"}, "body": True}, "require": ["number"], "to": "detail.status"},
        {"read": "milestone list", "args": {"module": {"arg": "module"}}, "to": "detail.milestones"},
        # 提出を処理できるか・できない理由（ボタンの灰色とツールチップ）
        {"can": "task approve", "args": {"module": {"arg": "module"}, "task": {"arg": "number"}}, "require": ["task"], "to": "detail.can_approve"},
        {"can": "task reject", "args": {"module": {"arg": "module"}, "task": {"arg": "number"}}, "require": ["task"], "to": "detail.can_reject"},
        {"can": "task finish", "args": {"module": {"arg": "module"}, "number": {"arg": "number"}}, "require": ["number"], "to": "detail.can_finish"},
        {"on": "detail.comment", "run": "task comment", "notify": "コメントしました。",
         "args": {"module": {"arg": "module"}, "number": {"payload": "id"}, "message": {"payload": "message"}}},
        # 提出：取り下げる（確かめてから）・手元で確認・取り込みを取り消す（確かめてから）。差分は提出の画面で
        {"on": "detail.withdraw", "run": "task withdraw", "args": {"module": {"arg": "module"}, "number": {"payload": "id"}}, "notify": "提出を取り下げました。"},
        {"on": "detail.review", "run": "task review", "args": {"module": {"arg": "module"}, "number": {"payload": "id"}}, "notify": "提出を、確認用の作業空間に取り出しました。",
         "after": {"open": "frame-workspace", "args": {"module": {"arg": "module"}, "space": {"result": "workspace"}}}},
        {"on": "detail.revert", "run": "task revert", "args": {"module": {"arg": "module"}, "number": {"payload": "id"}}, "notify": "取り込みを取り消すタスクを作りました。",
         # 取り消しが衝突で止まった：止まっている作業空間を開く（衝突の帯で、直して「続ける」と案内する）
         "instead": {"when": {"code": "merge_conflict"}, "open": "frame-workspace",
                     "args": {"module": {"arg": "module"}, "space": {"error": "details.workspace"}}}},
        # 差分：TortoiseGit で（前の GUI と同じ）。なければ、窓の中に文字で
        {"on": "detail.submission", "run": "task diff", "args": {"module": {"arg": "module"}, "task": {"payload": "id"}, "gui": True},
         "instead": {"when": {"code": "tool_missing"}, "open": "review-diff", "args": {"module": {"arg": "module"}, "task": {"payload": "id"}}, "inside": True}},
    ],
}
