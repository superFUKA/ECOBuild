"""入力の窓：タスク・提出にコメントする（ecobuild task comment --issue <番号> --message <文>）。

提出の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（使わない）

SCREEN = {
    "root": "page",
    "window": {"title": "コメント", "width": 560, "height": 380},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "#{issue} にコメント", "ok": "コメントする", "vars": {"issue": {"arg": "issue"}},
            "fields": [
                {"name": "message", "label": "内容", "type": "textarea", "rows": 5, "required": True},
            ]}},
    ],
    "bindings": [
        {"on": "form.submitted", "run": "task comment", "notify": "コメントしました。", "close": True, "require": ["message"],
         "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}, "message": {"payload": "values.message"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
