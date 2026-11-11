"""モジュール › テンプレート › 追加・差し替え：入力の窓。ファイルテンプレートを登録する（ecobuild template add <名前> <元のファイル>）。"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・差し替えるテンプレート（追加なら空）

SCREEN = {
    "root": "page",
    "window": {"title": "テンプレート", "width": 600, "height": 460},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "テンプレートを登録", "subject": {"arg": "name"}, "ok": "登録", "initial": {"place": {"arg": "module"}, "name": {"arg": "name"}},
            "vars": {"marks": "{{header}}・{{name}}・{{suite}}・{{project}}"},  # 文の中の {…} は置き換わるので、波かっこの文字は値として渡す
            "intro": "同じ名前のテンプレートがあれば差し替えます。ファイルの中の {marks} は、作るときに置き換わります。",
            "fields": [
                {"name": "name", "label": "名前（英字で始まる英数字と _）", "required": True},
                {"name": "source", "label": "元にするファイル（絶対パス、またはモジュールからの相対パス）", "required": True},
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        {"on": "form.submitted", "run": "template add", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "name": {"payload": "values.name"}, "source": {"payload": "values.source"}},
         "notify": "テンプレートを登録しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
