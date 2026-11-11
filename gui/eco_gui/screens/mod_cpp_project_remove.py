"""モジュール › Project › 削除：入力の窓。Project を外し、そのディレクトリを削除する（ecobuild project remove <名前>）。"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・削除する Project

SCREEN = {
    "root": "page",
    "window": {"title": "Projectを削除", "width": 600, "height": 400},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "Projectを削除", "subject": {"arg": "name"}, "ok": "削除", "danger": True, "initial": {"place": {"arg": "module"}},
            "intro": "Projectを外し、そのディレクトリを削除します。他のProjectからのリンクも外します。"
                     "最初に作ったProjectを外すと、他のモジュールからリンクできなくなります。",
            "fields": [
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        {"on": "form.submitted", "run": "project remove", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "name": {"arg": "name"}}, "notify": "Projectを削除しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
