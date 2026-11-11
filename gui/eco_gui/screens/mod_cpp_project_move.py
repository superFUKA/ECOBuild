"""モジュール › Project › 移動：入力の窓。Project のディレクトリを移す（ecobuild project move <名前> <移動先>）。名前は変わらない。"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・移す Project

SCREEN = {
    "root": "page",
    "window": {"title": "Projectを移動", "width": 600, "height": 400},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "Projectを移動", "subject": {"arg": "name"}, "ok": "移動", "initial": {"place": {"arg": "module"}}, "vars": {"name": {"arg": "name"}},
            "intro": "Projectのディレクトリを移します（名前は変わりません）。",
            "fields": [
                {"name": "destination", "label": "移動先のディレクトリ（モジュールからの相対。まだないもの）", "required": True, "placeholder": "例：libs/{name}"},
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        {"on": "form.submitted", "run": "project move", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "name": {"arg": "name"}, "destination": {"payload": "values.destination"}},
         "notify": "Projectを移しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
