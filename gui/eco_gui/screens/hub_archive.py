"""ハブ › 片付け：GitHub にあるモジュールをアーカイブ（読み取り専用）にする・解除する・削除する。"""

SCREEN = {
    "root": "page",
    "window": {"title": "モジュールの片付け", "width": 900, "height": 640},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "note", "modules", "chosen", "away_row", "delete_note", "delete_form"]},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "モジュールの片付け", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "note", "part": "note", "props": {
            "text": "使わなくなったモジュールは、まずアーカイブ（読み取り専用）にします。削除できるのは、アーカイブしたものだけです。片付けるモジュールを、表から選びます。"}},
        {"id": "modules", "part": "pick-rows", "props": {
            "columns": [{"key": "repository", "label": "リポジトリ"}, {"key": "type", "label": "型"}, {"key": "private", "label": "公開"},
                        {"key": "archived", "label": "状態"}, {"key": "description", "label": "説明"}],
            "key": "repository",
            "labels": {"private": {"true": "非公開", "false": "公開"}, "archived": {"true": "アーカイブ済み", "false": ""}},
            "empty_text": "GitHub にモジュールはありません。",
        }},
        {"id": "chosen", "part": "note", "props": {"prefix": "選んでいるモジュール："}},
        # 選んだモジュールの今の状態に合うボタンだけを出す（選ぶまでは、どれも出ない）
        {"id": "away_row", "layout": "row", "children": ["archive", "unarchive"]},
        {"id": "archive", "part": "button", "props": {"label": "アーカイブする"}},
        {"id": "unarchive", "part": "button", "props": {"label": "アーカイブを解除"}},
        {"id": "delete_note", "part": "note", "props": {
            "text": "削除すると、GitHub のリポジトリを Issue・PR ごと消します（90日以内なら GitHub のアカウントの設定から戻せます）。アーカイブ済みのモジュールを選ぶと、下に削除の欄が出ます。"}},
        {"id": "delete_form", "layout": "row", "children": ["confirm", "remove_workspaces", "delete"]},
        {"id": "confirm", "part": "text-input", "props": {
            "title": "削除の確かめ（取り違えないように、所有者/名前 を入力）", "placeholder": "例：owner/name"}},
        {"id": "remove_workspaces", "part": "select", "props": {"title": "この PC の作業空間", "options": [
            {"value": "", "label": "残す"}, {"value": "true", "label": "一緒に削除する"}]}},
        {"id": "delete", "part": "button", "props": {"label": "削除する"}},
    ],
    "bindings": [
        {"read": "module list", "args": {"all": True}, "to": "modules.rows"},
        {"on": "reload.pressed", "refresh": True},
        # 選んだ行のリポジトリと状態を、共有の値に（ボタンの引数と、出し分けに使う）
        {"on": "modules.selected", "set": {"away_module": {"payload": "id"}, "away_archived": {"payload": "row.archived"}}},
        {"value": "away_module", "to": "modules.selected"},
        {"value": "away_module", "to": "chosen.text"},
        {"show": "archive", "when": {"away_archived": False}},
        {"show": "unarchive", "when": {"away_archived": True}},
        {"show": "confirm", "when": {"away_archived": True}},
        {"show": "remove_workspaces", "when": {"away_archived": True}},
        {"show": "delete", "when": {"away_archived": True}},
        # ecobuild module archive <名前>・module unarchive <名前>・module delete <名前> --confirm <名前> [--remove-workspaces]
        # 実行できたら、状態の控えも合わせる（出すボタンが入れ替わる）
        {"on": "archive.pressed", "run": "module archive", "args": {"name": {"value": "away_module"}}, "set": {"away_archived": True}},
        {"on": "unarchive.pressed", "run": "module unarchive", "args": {"name": {"value": "away_module"}}, "set": {"away_archived": False}},
        # 削除の確かめ（--confirm）だけは、人が打った名前をそのまま渡す。選んだものと合っているかは ecobuild が確かめる
        {"on": "confirm.changed", "set": {"confirm": {"payload": "text"}}},
        {"on": "remove_workspaces.changed", "set": {"remove_workspaces": {"payload": "value"}}},
        {"on": "delete.pressed", "run": "module delete", "require": ["confirm"], "args": {
            "name": {"value": "away_module"}, "confirm": {"value": "confirm"}, "remove_workspaces": {"value": "remove_workspaces"}},
         "set": {"away_module": None, "away_archived": None, "confirm": None}},
    ],
}
