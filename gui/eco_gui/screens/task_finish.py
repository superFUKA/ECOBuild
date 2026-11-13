"""入力の窓：提出を取り込む（ecobuild task finish <番号> [--subject …] [--ignore-checks] --complete か --partial）。

タスク管理・提出の画面の中に重ねて開く。上に「何が起きるか」の表（「タスクを完了する」の印で、タスクの行が変わる）。
中間提出なら、初めは「タスクを完了する」が外れている。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（other：他人の提出を、承認せずに取り込む）

SCREEN = {
    "root": "page",
    "window": {"title": "取り込む", "width": 560, "height": 460},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "取り込む：#{issue}", "ok": "取り込む", "vars": {"issue": {"arg": "issue"}}, "tag": {"arg": "text"},
            "outcome": [
                {"label": "取り込み", "text": "CI を待って、提出を作成元（{base}）へ取り込みます"},
                {"label": "タスク", "text": "閉じて、タスクブランチを片付けます", "show_if": {"complete": True}},
                {"label": "タスク", "text": "閉じずに続けます（タスクブランチを作成元の最新から作り直します）", "show_if": {"complete": False}},
            ],
            "fields": [
                {"name": "subject", "label": "取り込むコミットの件名（空ならタスクの題名）"},
                {"name": "ignore_checks", "label": "CIが失敗していても取り込む", "type": "checkbox"},
                {"name": "complete", "label": "タスクを完了する", "type": "checkbox", "value_from": "pull_request.partial", "off_value": True,
                 "inverse": "partial"},
            ]}},
    ],
    "bindings": [
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}}, "to": "form.values"},
        {"on": "form.submitted", "run": "task finish", "confirmed": True, "notify": "取り込みました。[次の候補：#{next.number} {next.title}]", "close": True,
         "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "subject": {"payload": "values.subject"},
                  "ignore_checks": {"payload": "values.ignore_checks"}, "complete": {"payload": "values.complete"}, "partial": {"payload": "values.partial"}},
         # 作成元と衝突して止まった：自分の提出は「取り込んで直す」、他人の提出（承認せずに取り込む）は「差し戻す」の案内に
         "instead": [{"when": {"code": "pull_request_conflict"}, "input": {"tag": "other"}, "open": "task-conflict-reject", "here": True,
                      "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}, "files": {"error": "details"}}},
                     {"when": {"code": "pull_request_conflict"}, "open": "task-conflict-fix", "here": True,
                      "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}, "files": {"error": "details"}}}]},
        {"on": "form.cancelled", "close": True},
    ],
}
