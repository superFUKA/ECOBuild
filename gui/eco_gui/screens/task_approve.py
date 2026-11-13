"""入力の窓：提出を承認して取り込む（ecobuild task approve <番号> [--message …] [--subject …] [--ignore-checks]）。

タスク管理・提出の画面の中に重ねて開く。上に「何が起きるか」の表（中間提出かどうかで、タスクの行が変わる）。
うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（使わない）

SCREEN = {
    "root": "page",
    "window": {"title": "承認して取り込む", "width": 560, "height": 560},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "承認して取り込む：#{issue}", "ok": "承認して取り込む", "vars": {"issue": {"arg": "issue"}},
            "intro": "CIが終わるのを待ちます。タスクは提出のとおり閉じるか続けます。",
            "outcome": [
                {"label": "取り込み", "text": "提出を承認し、CI を待って作成元（{base}）へ取り込みます"},
                {"label": "タスク", "text": "閉じて、タスクブランチを片付けます", "hide_if": {"pull_request.partial": True}},
                {"label": "タスク", "text": "閉じずに続けます（タスクブランチを作成元の最新から作り直します）", "show_if": {"pull_request.partial": True}},
            ],
            "fields": [
                {"name": "message", "label": "コメント（任意）", "type": "textarea"},
                {"name": "subject", "label": "取り込むコミットの件名（空ならタスクの題名）"},
                {"name": "ignore_checks", "label": "CIが失敗していても取り込む", "type": "checkbox"},
            ]}},
    ],
    "bindings": [
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}}, "to": "form.values"},
        {"on": "form.submitted", "run": "task approve", "confirmed": True, "notify": "承認して取り込みました。[次の候補：#{next.number} {next.title}]", "close": True,
         "args": {"module": {"arg": "module"}, "task": {"arg": "issue"}, "message": {"payload": "values.message"},
                  "subject": {"payload": "values.subject"}, "ignore_checks": {"payload": "values.ignore_checks"}},
         "instead": {"when": {"code": "pull_request_conflict"}, "open": "task-conflict-reject", "here": True,
                     "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}, "files": {"error": "details"}}}},
        {"on": "form.cancelled", "close": True},
    ],
}
