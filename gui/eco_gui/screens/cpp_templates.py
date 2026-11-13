"""設定 › ファイルテンプレート：新しいファイルのひな型（ecobuild template add・remove）。

C++ のモジュールの「設定」のタブに置く（部品 mod-cpp。変える操作は、入力の窓を重ねて開く）。
"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "templates",
    "nodes": [
        {"id": "templates", "part": "mod-cpp", "props": {"view": "templates"}},
    ],
    "bindings": [
        {"on": "templates.reload", "refresh": True},
        # 作業空間がなければ、変える操作は灰色と「今は見るだけ」の帯（そこから、タスク管理を開く）
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "templates.workspaces", "from": "workspaces"},
        {"on": "templates.action", "when": {"name": "open_tasks"}, "open": "tasks", "args": {"module": {"arg": "module"}}, "here": True},
        {"read": "module settings", "args": {"module": {"arg": "module"}}, "to": "templates.settings"},
        {"on": "templates.action", "when": {"name": "template_add"}, "open": "mod-cpp-template-add", "inside": True, "args": {"module": {"arg": "module"}}},
        {"on": "templates.action", "when": {"name": "template_replace"}, "open": "mod-cpp-template-add", "inside": True, "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},
        {"on": "templates.action", "when": {"name": "template_remove"}, "open": "mod-cpp-template-remove", "inside": True, "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},
    ],
}
