"""入力の窓：提出（PR）を作らずに、作成元へ反映する（ecobuild task apply --task <番号> [--subject …] [--partial]）。

提出の画面の中に重ねて開く。上に「何が起きるか」の表（「タスクを完了する」の印で、反映した後の行が変わる）。
うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（使わない）

SCREEN = {
    "root": "page",
    "window": {"title": "反映", "width": 560, "height": 460},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "反映：#{issue}", "ok": "反映", "vars": {"issue": {"arg": "issue"}},
            "outcome": [
                {"label": "反映", "text": "提出（PR）を作らずに、作成元（{base}）の最新へ1つのコミットにまとめて入れます（CIは待ちません）"},
                {"label": "提出", "text": "開いている提出は、取り込まずに閉じます", "show_if": {"pull_request.state": "open"}},
                {"label": "衝突したら", "text": "何もせずに止まります"},
                {"label": "反映したら", "text": "閉じて、タスクブランチを片付けます", "show_if": {"complete": True}},
                {"label": "反映したら", "text": "閉じずに続けます（タスクブランチを作成元の最新から作り直します）", "show_if": {"complete": False}},
            ],
            "fields": [
                {"type": "note", "list_from": "commits", "list_as": "commits", "label": "提出に入るコミット（{commits.length}件、新しい順）",
                 "empty_text": "提出に入るコミットはありません（作成元と同じです）。"},
                {"name": "subject", "label": "取り込むコミットの件名（空ならタスクの題名）"},
                {"name": "complete", "label": "タスクを完了する", "type": "checkbox", "value_from": "pull_request.partial", "off_value": True,
                 "inverse": "partial"},
            ]}},
    ],
    "bindings": [
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}}, "to": "form.values"},
        {"on": "form.submitted", "run": "task apply", "confirmed": True, "notify": "反映しました。", "close": True,
         "args": {"module": {"arg": "module"}, "task": {"arg": "issue"}, "subject": {"payload": "values.subject"}, "partial": {"payload": "values.partial"}},
         "instead": {"when": {"code": "merge_conflict"}, "open": "task-conflict-fix", "here": True,
                     "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}, "title": "反映できません"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
