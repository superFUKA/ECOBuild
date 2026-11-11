"""ハブ › モジュールを追加：新規作成・GitHub から取得・手元のフォルダを登録・リポジトリをモジュールに。ハブの窓の中に重ねて開く。"""

SCREEN = {
    "root": "page",
    "window": {"title": "モジュールを追加", "width": 640, "height": 720},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["title", "form", "actions"]},
        {"id": "title", "part": "note", "props": {"text": "モジュールを追加", "heading": True}},
        {"id": "form", "part": "hub-add-form", "look": "grow"},
        # 選んでいる方法のボタンだけを出す
        {"id": "actions", "layout": "row", "look": "actions", "children": ["cancel", "create", "clone", "register", "adopt"]},
        {"id": "cancel", "part": "button", "props": {"label": "キャンセル"}},
        {"id": "create", "part": "button", "props": {"label": "作成する", "primary": True}},
        {"id": "clone", "part": "button", "props": {"label": "取得する", "primary": True}},
        {"id": "register", "part": "button", "props": {"label": "登録する", "primary": True}},
        {"id": "adopt", "part": "button", "props": {"label": "モジュールにする…", "primary": True}},
    ],
    "bindings": [
        {"read": "module types", "to": "form.types"},
        {"read": "workspace list", "to": "form.modules", "from": "modules"},
        {"read": "config list", "to": "form.owner", "from": "owner"},
        {"read": "module list", "args": {"all": True}, "to": "form.candidates"},
        {"on": "form.changed", "set": {
            "add_method": {"payload": "method"}, "add_directory": {"payload": "directory"}, "add_name": {"payload": "name"},
            "add_type": {"payload": "type"}, "add_kind": {"payload": "kind"}, "add_project": {"payload": "project"}, "add_test": {"payload": "test"},
            "add_description": {"payload": "description"}, "add_owner": {"payload": "owner"}, "add_public": {"payload": "public"},
            "add_repository": {"payload": "repository"}, "add_folder": {"payload": "folder"},
            "add_adopt_folder": {"payload": "adopt_folder"}, "add_adopt_type": {"payload": "adopt_type"}}},
        {"show": "create", "when": {"add_method": ["new", None]}},
        {"show": "clone", "when": {"add_method": "clone"}},
        {"show": "register", "when": {"add_method": "register"}},
        {"show": "adopt", "when": {"add_method": "adopt"}},
        {"value": "add_problem", "to": "form.problem"},
        {"on": "cancel.pressed", "close": True},
        # 新規作成：保存先の親フォルダで ecobuild module new <名前> --type <型> [--kind …] [--project …] [--no-test] [--description …] [--owner …] [--public]
        {"on": "create.pressed", "run": "module new", "require": ["module", "name"], "args": {
            "module": {"value": "add_directory"}, "name": {"value": "add_name"}, "type": {"value": "add_type"}, "kind": {"value": "add_kind"},
            "project": {"value": "add_project"}, "test": {"value": "add_test"}, "description": {"value": "add_description"},
            "owner": {"value": "add_owner"}, "public": {"value": "add_public"}},
         "set": {"add_problem": None}, "failed": {"add_problem": {"error": "message"}}, "notify": "モジュールを作成しました。", "close": True},
        # 取得：保存先の親フォルダで ecobuild module clone <所有者/名前>
        {"on": "clone.pressed", "run": "module clone", "require": ["module", "repository"], "args": {
            "module": {"value": "add_directory"}, "repository": {"value": "add_repository"}},
         "set": {"add_problem": None}, "failed": {"add_problem": {"error": "message"}}, "notify": "モジュールを取得しました。", "close": True},
        # 登録：ecobuild workspace add <フォルダー>
        {"on": "register.pressed", "run": "workspace add", "args": {"path": {"value": "add_folder"}},
         "set": {"add_problem": None}, "failed": {"add_problem": {"error": "message"}}, "notify": "一覧に登録しました。", "close": True},
        # モジュールにする：そのフォルダで ecobuild module adopt --type <型>（置くファイルと push 先は、実行する前の確かめに出る）
        {"on": "adopt.pressed", "run": "module adopt", "require": ["module"], "args": {
            "module": {"value": "add_adopt_folder"}, "type": {"value": "add_adopt_type"}},
         "set": {"add_problem": None}, "failed": {"add_problem": {"error": "message"}}, "notify": "モジュールにしました（push 済み）。", "close": True},
    ],
}
