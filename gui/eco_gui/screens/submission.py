"""提出：1つのタスクの提出。状態・CI・入るコミット・やりとりを見て、確認・承認・差し戻し・取り下げ・取り込みをする。

どのボタンを出すか・押せるかは、部品が、読んだ答えのとおりに出す：自分の提出か（担当者が自分）、処理できるか（account show の
take_in）、確認中の作業空間があるか（module show の workspaces の review）。入力の要る操作は、入力の窓（review_form）を重ねて開く。
"""

ARGS = {"module": ".", "task": ""}  # モジュールのフォルダー・タスクの番号（表の行の ID のまま、文字で受ける。コマンドへは数で渡る）

SCREEN = {
    "root": "page",
    "window": {"title": "提出", "width": 900, "height": 820, "refresh": {"focus": True, "every": 180}},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "detail"]},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "close"]},
        {"id": "title", "part": "note", "props": {"text": "提出", "heading": True}},
        {"id": "close", "part": "button", "props": {"label": "閉じる"}},
        {"id": "detail", "part": "review-submission"},
    ],
    "bindings": [
        # 読む：タスクの提出（ecobuild task status <番号>）・アカウント・作業空間
        {"read": "task status", "args": {"module": {"arg": "module"}, "issue": {"arg": "task"}}, "to": "detail.task"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "detail.access"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "detail.spaces", "from": "workspaces"},
        {"on": "close.pressed", "close": True},
        # 見る
        {"on": "detail.action", "when": {"action": "refresh"}, "refresh": True},
        {"on": "detail.action", "when": {"action": "diff"}, "open": "review-diff", "inside": True,
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}}},
        {"on": "detail.action", "when": {"action": "task"}, "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
        {"on": "detail.action", "when": {"action": "open_review"}, "open": "workspace", "args": {"module": {"payload": "workspace"}}},
        # 手元で確認（ecobuild task review --task <番号> [--done]）・取り下げ（ecobuild task withdraw --task <番号>。確かめてから）
        {"on": "detail.action", "when": {"action": "review"}, "run": "task review",
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}},
         "notify": "提出を、確認用の作業空間に取り出しました。そこでビルド・テスト・実行して確かめ、ここで承認か差し戻しをします。"},
        {"on": "detail.action", "when": {"action": "review_done"}, "run": "task review",
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}, "done": True}, "notify": "確認を終え、確認用の作業空間を消しました。"},
        {"on": "detail.action", "when": {"action": "withdraw"}, "run": "task withdraw",
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}}, "notify": "提出を取り下げました。"},
        # 入力の要る操作：入力の窓を重ねて開く（何が起きるかの表つき）
        {"on": "detail.action", "when": {"action": "comment"}, "open": "review-form", "inside": True,
         "args": {"module": {"arg": "module"}, "kind": "comment", "id": {"payload": "id"}}},
        {"on": "detail.action", "when": {"action": "reject"}, "open": "review-form", "inside": True,
         "args": {"module": {"arg": "module"}, "kind": "reject", "id": {"payload": "id"}}},
        {"on": "detail.action", "when": {"action": "approve"}, "open": "review-form", "inside": True,
         "args": {"module": {"arg": "module"}, "kind": "approve", "id": {"payload": "id"}, "base": {"payload": "base"}, "partial": {"payload": "partial"}}},
        {"on": "detail.action", "when": {"action": "finish"}, "open": "review-form", "inside": True,
         "args": {"module": {"arg": "module"}, "kind": "finish", "id": {"payload": "id"}, "base": {"payload": "base"}, "partial": {"payload": "partial"}}},
        {"on": "detail.action", "when": {"action": "apply"}, "open": "review-form", "inside": True,
         "args": {"module": {"arg": "module"}, "kind": "apply", "id": {"payload": "id"}, "base": {"payload": "base"}}},
    ],
}
