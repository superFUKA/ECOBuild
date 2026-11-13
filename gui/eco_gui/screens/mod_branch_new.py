"""モジュール › ブランチ › 作成：入力の窓。名前と作成元（共有ブランチから選ぶ）を決めて、ブランチを作る。"""

ARGS = {"module": ".", "base": ""}  # モジュールのフォルダー・作成元の初めの値（選んでいたブランチ）

SCREEN = {
    "root": "page",
    "window": {"title": "ブランチを作成", "width": 560, "height": 360},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "ブランチを作成", "ok": "作成", "initial": {"base": {"arg": "base"}},
            "fields": [
                {"name": "name", "label": "ブランチ名（task/ で始まる名前はタスクブランチ専用）", "type": "text", "required": True, "placeholder": "例：develop"},
                {"name": "base", "label": "作成元", "type": "select", "options_from": {"source": "rows", "where": {"is_task_branch": False}},
                 "none_label": "既定（default_base）"},
            ]}},
    ],
    "bindings": [
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "form.rows"},
        # 人が打つのと同じ：ecobuild branch create <名前> [--base <作成元>]
        {"on": "form.submitted", "run": "branch create",
         "args": {"module": {"arg": "module"}, "name": {"payload": "values.name"}, "base": {"payload": "values.base"}},
         "notify": "ブランチを作成しました。", "close": True, "parent": {"branch": {"payload": "values.name"}}},  # 作ったブランチを選ぶ
        {"on": "form.cancelled", "close": True},
    ],
}
