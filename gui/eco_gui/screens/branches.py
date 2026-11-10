"""モジュール › ブランチ：ブランチの一覧。作る・消す。取り込み・提出の画面を開く。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "ブランチ", "width": 1280, "height": 820},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "list", "form"]},
        {"id": "nav", "screen": "menu", "args": {"current": "branches", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "ブランチ", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "list", "part": "table", "props": {
            "columns": [{"key": "name", "label": "名前"}, {"key": "base", "label": "作成元"}, {"key": "local", "label": "手元"},
                        {"key": "remote", "label": "GitHub"}, {"key": "merged", "label": "取り込み"}],
            "key": "name",
            "labels": {"local": {"true": "ある", "false": ""}, "remote": {"true": "ある", "false": ""},
                       "merged": {"true": "済み", "false": ""}},
            "actions": [{"name": "merge", "label": "取り込み・提出…"}, {"name": "delete", "label": "消す"}],
            "empty_text": "ブランチはありません。",
        }},
        {"id": "form", "layout": "row", "children": ["name", "base", "create"]},
        {"id": "name", "part": "text-input", "props": {"title": "新しいブランチの名前", "placeholder": "例：dev"}},
        {"id": "base", "part": "text-input", "props": {"title": "作成元（空なら既定）", "placeholder": "例：main"}},
        {"id": "create", "part": "button", "props": {"label": "＋ 作る", "primary": True}},
    ],
    "bindings": [
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "list.rows"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "name.changed", "set": {"name": {"payload": "text"}}},
        {"on": "base.changed", "set": {"base": {"payload": "text"}}},
        {"value": "name", "to": "name.text"},  # 作ったら、欄は空に戻る
        {"value": "base", "to": "base.text"},
        {"on": "create.pressed", "run": "branch create", "args": {"module": {"arg": "module"}, "name": {"value": "name"}, "base": {"value": "base"}},
         "set": {"name": None, "base": None}},
        # このブランチを別のブランチへ取り込む・提出する画面（同じ窓で切り替える）
        {"on": "list.action", "when": {"action": "merge"}, "open": "merge",
         "args": {"module": {"arg": "module"}, "name": {"payload": "id"}}, "here": True},
        {"on": "list.action", "when": {"action": "delete"}, "run": "branch delete", "args": {"module": {"arg": "module"}, "name": {"payload": "id"}}},
    ],
}
