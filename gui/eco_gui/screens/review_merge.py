"""入力の窓：ブランチ同士の提出を取り込む（ecobuild branch merge <ブランチ> [--ignore-checks]）。

ブランチの提出・取り込みの画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・取り込むブランチ（提出の元）

SCREEN = {
    "root": "page",
    "window": {"title": "提出を取り込む", "width": 560, "height": 320},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "{name} の提出を取り込む", "ok": "取り込む", "vars": {"name": {"arg": "name"}},
            "intro": "ブランチ同士の提出を、マージコミットで取り込みます。",
            "fields": [
                {"name": "ignore_checks", "label": "CIが失敗していても取り込む", "type": "checkbox"},
            ]}},
    ],
    "bindings": [
        {"on": "form.submitted", "run": "branch merge", "notify": "ブランチの提出を取り込みました。", "close": True,
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "ignore_checks": {"payload": "values.ignore_checks"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
