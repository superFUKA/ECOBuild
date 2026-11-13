"""ビルド設定の Project ごとの上書きを外す（入力の窓）：変更するタスクブランチ（作業空間）を選んで外す
（ecobuild profile project <ビルド設定> <Project> --clear）。"""

ARGS = {"module": ".", "name": "", "project": ""}  # モジュールのフォルダー・ビルド設定・上書きを外す Project

SCREEN = {
    "root": "page",
    "window": {"title": "上書きを外す", "width": 600, "height": 360},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "上書きを外す", "subject": {"arg": "project"}, "ok": "外す", "initial": {"place": {"arg": "module"}},
            "intro": "ビルド設定の、この Project だけの上書きを外します（ビルド設定のとおりに戻ります）。",
            "fields": [
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        {"on": "form.submitted", "run": "profile project", "require": ["module"], "confirmed": True,
         "args": {"module": {"payload": "values.place"}, "name": {"arg": "name"}, "project": {"arg": "project"}, "clear": True},
         "notify": "上書きを外しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
