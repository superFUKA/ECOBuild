"""入力の窓：ラベルを付ける（ecobuild task edit <番号> --add-label <ラベル>）。

タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（使わない）

SCREEN = {
    "root": "page",
    "window": {"title": "ラベルを付ける", "width": 560, "height": 300},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "ラベルを付ける：#{issue}", "ok": "付ける", "vars": {"issue": {"arg": "issue"}},
            "fields": [
                {"name": "label", "label": "ラベル（カンマ区切り。なければ作ります）", "required": True},
            ]}},
    ],
    "bindings": [
        {"on": "form.submitted", "run": "task edit", "notify": "保存しました。", "close": True, "require": ["add_label"],
         "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}, "add_label": {"payload": "values.label"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
