"""モジュール › 依存先 › リンクを外す：入力の窓。依存先のリンクを外す（ecobuild deps remove <名前>）。"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・外す依存先

SCREEN = {
    "root": "page",
    "window": {"title": "リンクを外す", "width": 600, "height": 400},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "リンクを外す", "subject": {"arg": "name"}, "ok": "外す", "danger": True, "initial": {"place": {"arg": "module"}},
            "intro": "依存先のリンクを外します。手元のcloneは、記録の版のままなら削除します（作業中や変更がある場合は残します）。",
            "fields": [
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        {"on": "form.submitted", "run": "deps remove", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "name": {"arg": "name"}}, "notify": "リンクを外しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
