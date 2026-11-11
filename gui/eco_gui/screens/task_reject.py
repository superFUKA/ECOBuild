"""入力の窓：提出を差し戻す（ecobuild task reject <番号> --message <直してほしいこと>）。

タスク管理・提出の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（使わない）

SCREEN = {
    "root": "page",
    "window": {"title": "差し戻す", "width": 560, "height": 400},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "差し戻す：#{issue}", "ok": "差し戻す", "danger": True, "vars": {"issue": {"arg": "issue"}},
            "intro": "タスクは作業中に戻ります。",
            "fields": [
                {"name": "message", "label": "直してほしいこと", "type": "textarea", "rows": 5, "required": True},
            ]}},
    ],
    "bindings": [
        {"on": "form.submitted", "run": "task reject", "notify": "差し戻しました。", "close": True, "require": ["message"],
         "args": {"module": {"arg": "module"}, "task": {"arg": "issue"}, "message": {"payload": "values.message"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
