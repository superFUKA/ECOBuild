"""ハブ › 片付け：GitHub にあるモジュールをアーカイブ（読み取り専用）にする・解除する・削除する。"""

SCREEN = {
    "root": "page",
    "window": {"title": "モジュールの片付け", "width": 900, "height": 640},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "note", "modules", "delete_note", "delete_form"]},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "モジュールの片付け", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "note", "part": "note", "props": {
            "text": "使わなくなったモジュールは、まずアーカイブ（読み取り専用）にします。削除できるのは、アーカイブしたものだけです。"}},
        {"id": "modules", "part": "table", "props": {
            "columns": [{"key": "repository", "label": "リポジトリ"}, {"key": "type", "label": "型"}, {"key": "private", "label": "公開"},
                        {"key": "archived", "label": "状態"}, {"key": "description", "label": "説明"}],
            "key": "repository",
            "actions": [{"name": "archive", "label": "アーカイブ"}, {"name": "unarchive", "label": "解除"}, {"name": "delete", "label": "削除"}],
            "labels": {"private": {"true": "非公開", "false": "公開"}, "archived": {"true": "アーカイブ済み", "false": ""}},
            "empty_text": "GitHub にモジュールはありません。",
        }},
        {"id": "delete_note", "part": "note", "props": {
            "text": "削除すると、GitHub のリポジトリを Issue・PR ごと消します（90日以内なら GitHub のアカウントの設定から戻せます）。取り違えないように、削除するモジュールを下に入力してから、その行の「削除」を押します。"}},
        {"id": "delete_form", "layout": "row", "children": ["confirm", "remove_workspaces"]},
        {"id": "confirm", "part": "text-input", "props": {"title": "削除するモジュール（所有者/名前）", "placeholder": "例：owner/name"}},
        {"id": "remove_workspaces", "part": "select", "props": {"title": "この PC の作業空間", "options": [
            {"value": "", "label": "残す"}, {"value": "true", "label": "一緒に削除する"}]}},
    ],
    "bindings": [
        {"read": "module list", "args": {"all": True}, "to": "modules.rows"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "confirm.changed", "set": {"confirm": {"payload": "text"}}},
        {"on": "remove_workspaces.changed", "set": {"remove_workspaces": {"payload": "value"}}},
        # 行のボタン（ecobuild module archive <名前>・module unarchive <名前>・module delete <名前> --confirm <名前> [--remove-workspaces]）
        # 削除の確かめ（--confirm）には、人が打った名前をそのまま渡す。行と合っているかは ecobuild が確かめる
        {"on": "modules.action", "when": {"action": "archive"}, "run": "module archive", "args": {"name": {"payload": "id"}}},
        {"on": "modules.action", "when": {"action": "unarchive"}, "run": "module unarchive", "args": {"name": {"payload": "id"}}},
        {"on": "modules.action", "when": {"action": "delete"}, "run": "module delete", "args": {
            "name": {"payload": "id"}, "confirm": {"value": "confirm"}, "remove_workspaces": {"value": "remove_workspaces"}}},
    ],
}
