"""モジュール › テンプレート › 削除：入力の窓。このモジュールのファイルテンプレートを消す（ecobuild template remove <名前>）。"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・消すテンプレート

SCREEN = {
    "root": "page",
    "window": {"title": "テンプレートを削除", "width": 600, "height": 360},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "テンプレートを削除", "subject": {"arg": "name"}, "ok": "削除", "danger": True, "initial": {"place": {"arg": "module"}},
            "fields": [
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        {"on": "form.submitted", "run": "template remove", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "name": {"arg": "name"}}, "notify": "テンプレートを削除しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
