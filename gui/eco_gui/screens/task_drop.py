"""入力の窓：作業を取り込まずに捨てる（ecobuild task drop <番号> [--close]）。

タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（使わない）

SCREEN = {
    "root": "page",
    "window": {"title": "作業を捨てる", "width": 560, "height": 340},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "作業を捨てる：#{issue}", "ok": "作業を捨てる", "danger": True, "vars": {"issue": {"arg": "issue"}},
            "intro": "作業を取り込まずに捨てます。提出を閉じ、タスクブランチをこのPCとGitHubから消して、その作業空間も消します。捨てた作業は戻せません。",
            "fields": [
                {"name": "close", "label": "タスクも削除する", "type": "checkbox"},
            ]}},
    ],
    "bindings": [
        {"on": "form.submitted", "run": "task drop", "notify": "作業を捨てました。", "close": True,
         "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "close": {"payload": "values.close"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
