"""モジュール › 依存先 › 更新・版を記録：入力の窓。依存先の記録を、GitHub の最新（か、選んだ版）にする
（ecobuild deps update [--name <名前>] [--at <版>]）。名前が空なら、すべての依存先。
"""

ARGS = {"module": ".", "name": "", "at": ""}  # モジュールのフォルダー・更新する依存先（空なら全部）・記録する版（空なら最新）

SCREEN = {
    "root": "page",
    "window": {"title": "依存先を更新", "width": 600, "height": 460},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "依存先を更新", "subject": {"arg": "name"}, "ok": "更新",
            "initial": {"place": {"arg": "module"}, "name": {"arg": "name"}, "at": {"arg": "at"}},
            "intro": "依存先の記録を GitHub の最新（版を書けば、その版）にし、手元の clone と生成ファイルも合わせます。",
            "fields": [
                {"name": "name", "label": "依存先（空なら、すべて）", "row": "what"},
                {"name": "at", "label": "記録する版（ブランチ・タグ・コミット。空なら最新）", "row": "what"},
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        {"on": "form.submitted", "run": "deps update", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "name": {"payload": "values.name"}, "at": {"payload": "values.at"}},
         "notify": "依存先を更新しました。", "close": True, "parent": {"cpp_versions": None}},
        {"on": "form.cancelled", "close": True},
    ],
}
