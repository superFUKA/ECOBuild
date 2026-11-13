"""入力の窓：タスクを完了にする：まだ取り込んでいない変更を取り込んでから閉じる（ecobuild task finish <番号> --complete [--ignore-checks]）。

タスク管理の画面の中に重ねて開く。上に「何が起きるか」の表（提出を出しているかどうかで、取り込みの行が変わる）。
うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（使わない）

SCREEN = {
    "root": "page",
    "window": {"title": "完了にする", "width": 560, "height": 380},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "完了にする：#{issue}", "ok": "完了にする", "vars": {"issue": {"arg": "issue"}},
            "outcome": [
                {"label": "取り込み", "text": "出している提出を、CI を待って作成元（{base}）へ取り込みます", "show_if": {"pull_request.state": "open"}},
                {"label": "取り込み", "text": "まだ取り込んでいない変更があれば、提出して作成元（{base}）へ取り込みます（なければ取り込みません）",
                 "hide_if": {"pull_request.state": "open"}},
                {"label": "タスク", "text": "閉じて、タスクブランチを片付けます"},
            ],
            "fields": [
                {"name": "ignore_checks", "label": "CIが失敗していても完了する", "type": "checkbox"},
            ]}},
    ],
    "bindings": [
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}}, "to": "form.values"},
        {"on": "form.submitted", "run": "task finish", "confirmed": True, "notify": "完了にしました。[次の候補：#{next.number} {next.title}]", "close": True,
         "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "ignore_checks": {"payload": "values.ignore_checks"}, "complete": True},
         "instead": {"when": {"code": "pull_request_conflict"}, "open": "task-conflict-fix", "here": True,
                     "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}, "files": {"error": "details"}}}},
        {"on": "form.cancelled", "close": True},
    ],
}
