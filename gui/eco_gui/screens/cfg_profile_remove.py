"""ビルド設定を削除（入力の窓）：消すビルド設定を確かめ、変更するタスクブランチ（作業空間）を選んで消す（ecobuild profile remove <名前>）。"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・消すビルド設定

SCREEN = {
    "root": "page",
    "window": {"title": "ビルド設定を削除", "width": 600, "height": 360},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "ビルド設定を削除", "subject": {"arg": "name"}, "ok": "削除", "danger": True, "initial": {"place": {"arg": "module"}},
            "intro": "ecobuild.toml からビルド設定を消します。タスクブランチでコミットし、PRで反映してください。",
            "fields": [
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        {"on": "form.submitted", "run": "profile remove", "require": ["module"], "confirmed": True,
         "args": {"module": {"payload": "values.place"}, "name": {"arg": "name"}}, "notify": "ビルド設定を削除しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
