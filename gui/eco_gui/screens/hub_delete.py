"""ハブ › アーカイブ済みのモジュールを削除する：GitHub のリポジトリを Issue・PR ごと消す。取り違えないよう、所有者/名前 を打って確かめる。"""

ARGS = {"repository": "", "local": ""}

SCREEN = {
    "root": "page",
    "window": {"title": "モジュールを削除", "width": 580, "height": 560},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["title", "note", "local", "remove_workspaces", "discard_local", "confirm", "problem", "actions"]},
        {"id": "title", "part": "note", "props": {"text": {"arg": "repository"}, "prefix": "モジュールを削除：", "heading": True}},
        {"id": "note", "part": "note", "props": {"text": "アーカイブ済みのモジュールです。削除すると、GitHub のリポジトリを Issue・PR ごと消します。削除したリポジトリは、90日以内なら GitHub のアカウント設定から復元できます。タスク管理の情報は削除せずに閉じ、復元したときに引き継ぎます。"}},
        {"id": "local", "part": "note", "props": {"text": {"arg": "local"}, "prefix": "この PC の clone：", "tone": "muted"}},
        {"id": "remove_workspaces", "part": "toggle", "props": {"label": "この PC の clone・作業空間も削除する"}},
        {"id": "discard_local", "part": "toggle", "props": {
            "label": "GitHub にない変更・コミット・退避があっても削除する", "hint": "それらは失われます。チェックしなければ、ある場合は中止します"}},
        {"id": "confirm", "part": "text-input", "props": {
            "title": "確認のため、削除するリポジトリ（所有者/名前）を入力（空のまま押すと、開いている Issue・PR の数を確かめるだけ）", "placeholder": {"arg": "repository"}}},
        {"id": "problem", "part": "note", "props": {"tone": "bad"}},
        {"id": "actions", "layout": "row", "look": "actions", "children": ["cancel", "delete"]},
        {"id": "cancel", "part": "button", "props": {"label": "キャンセル"}},
        {"id": "delete", "part": "button", "props": {"label": "削除する", "danger": True}},
    ],
    "bindings": [
        {"on": "cancel.pressed", "close": True},
        {"on": "remove_workspaces.changed", "set": {"remove_workspaces": {"payload": "on"}}},
        {"on": "discard_local.changed", "set": {"discard_local": {"payload": "on"}}},
        {"show": "discard_local", "when": {"remove_workspaces": True}},  # clone を消すときだけ意味がある
        {"on": "confirm.changed", "set": {"confirm": {"payload": "text"}}},
        {"value": "delete_problem", "to": "problem.text"},
        # ecobuild module delete <所有者/名前> --confirm <打った名前> [--remove-workspaces [--discard-local]]。打った名前が合うかは ecobuild が確かめる
        # （名前を打たずに押すと、ecobuild は消さずに、開いている Issue・PR の数を答える。それを窓の中に出す）
        {"on": "delete.pressed", "run": "module delete", "args": {
            "name": {"arg": "repository"}, "confirm": {"value": "confirm"},
            "remove_workspaces": {"value": "remove_workspaces"}, "discard_local": {"value": "discard_local"}},
         "failed": {"delete_problem": {"error": "message"}},
         "notify": "削除しました（90日以内なら GitHub のアカウント設定から復元できます）。", "close": True},
    ],
}
