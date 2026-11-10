"""ハブ：この PC にあるモジュールの一覧。選ぶと、そのモジュールの窓を開く。"""

SCREEN = {
    "root": "page",
    "window": {"title": "ECOBuild", "width": 900, "height": 720},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "modules", "add_title", "register", "clone", "create"]},
        {"id": "head", "layout": "row", "children": ["title", "reload", "doctor"]},
        {"id": "doctor", "part": "button", "props": {"label": "環境チェック"}},
        {"id": "add_title", "part": "note", "props": {"text": "モジュールを足す"}},
        {"id": "register", "layout": "row", "children": ["path", "do_register"]},
        {"id": "path", "part": "text-input", "props": {"title": "この PC にあるモジュールのフォルダー", "placeholder": "例：C:\\work\\Calc"}},
        {"id": "do_register", "part": "button", "props": {"label": "一覧に足す"}},
        {"id": "clone", "layout": "row", "children": ["repository", "do_clone"]},
        {"id": "repository", "part": "text-input", "props": {"title": "GitHub のリポジトリ", "placeholder": "例：owner/name"}},
        {"id": "do_clone", "part": "button", "props": {"label": "取得する"}},
        {"id": "create", "layout": "row", "children": ["name", "type", "do_create"]},
        {"id": "name", "part": "text-input", "props": {"title": "新しいモジュールの名前", "placeholder": "例：Calc"}},
        {"id": "type", "part": "select", "props": {"title": "型", "options": [
            {"value": "", "label": "（既定）"}, {"value": "cpp", "label": "C++"}, {"value": "python", "label": "Python"},
            {"value": "generic", "label": "そのほか"}]}},
        {"id": "do_create", "part": "button", "props": {"label": "作る", "hint": "GitHub のリポジトリを作り、今のフォルダーの下に取り出す"}},
        {"id": "title", "part": "note", "props": {"text": "モジュール", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "modules", "part": "table", "props": {
            "columns": [{"key": "path", "label": "場所"}, {"key": "type", "label": "型"}, {"key": "branch", "label": "ブランチ"}],
            "key": "path",
            "actions": [{"name": "open", "label": "開く"}, {"name": "forget", "label": "一覧から外す"}],
            "empty_text": "モジュールはまだありません。",
        }},
    ],
    "bindings": [
        {"read": "workspace list", "to": "modules.rows", "from": "modules"},
        {"on": "reload.pressed", "refresh": True},
        # 選んだモジュールの窓を開く（モジュールごとに1つ。開いていれば前に出る）
        {"on": "modules.action", "when": {"action": "open"}, "open": "overview", "args": {"module": {"payload": "id"}}},
        {"on": "modules.action", "when": {"action": "forget"}, "run": "workspace forget", "args": {"path": {"payload": "id"}}},
        {"on": "doctor.pressed", "open": "doctor"},
        # 足す（ecobuild workspace add <フォルダー>・ecobuild module clone <リポジトリ>・ecobuild module new <名前> --type <型>）
        {"on": "path.changed", "set": {"path": {"payload": "text"}}},
        {"on": "do_register.pressed", "run": "workspace add", "args": {"path": {"value": "path"}}},
        {"on": "repository.changed", "set": {"repository": {"payload": "text"}}},
        {"on": "do_clone.pressed", "run": "module clone", "args": {"repository": {"value": "repository"}}},
        {"on": "name.changed", "set": {"name": {"payload": "text"}}},
        {"on": "type.changed", "set": {"type": {"payload": "value"}}},
        {"on": "do_create.pressed", "run": "module new", "args": {"name": {"value": "name"}, "type": {"value": "type"}}},
    ],
}
