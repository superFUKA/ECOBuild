"""モジュール › 概要：README と、横に「このモジュール」（GitHub・型・Project・依存先）。下に、タスクの作業空間。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "ECOBuild", "width": 1280, "height": 820, "refresh": {"focus": True}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "section", "home"]},
        {"id": "section", "screen": "mod-tabs", "args": {"current": "overview", "module": {"arg": "module"}}},
        {"id": "nav", "screen": "menu", "args": {"current": "overview", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "tools"]},
        {"id": "title", "part": "note", "props": {"text": "モジュール", "heading": True}},
        {"id": "tools", "layout": "row", "look": "tools", "children": ["reload", "open_here"]},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        {"id": "open_here", "part": "button", "props": {"label": "この場所の作業空間を開く"}},
        # 左：README と作業空間。右：このモジュール
        {"id": "home", "layout": "row", "look": "mod-home", "children": ["left", "about"]},
        {"id": "left", "layout": "column", "children": ["readme", "spaces_title", "spaces"]},
        {"id": "readme", "part": "mod-readme"},
        {"id": "about", "part": "mod-about"},
        {"id": "spaces_title", "part": "note", "props": {"text": "タスクの作業空間", "tone": "section"}},
        {"id": "spaces", "part": "table", "props": {
            "columns": [{"key": "task", "label": "タスク"}, {"key": "branch", "label": "ブランチ"}, {"key": "path", "label": "場所"}],
            "key": "path", "actions": [{"name": "open", "label": "開く"}],
            "empty_text": "タスクの作業空間はありません。",
        }},
    ],
    "bindings": [
        {"read": "module readme", "args": {"module": {"arg": "module"}}, "to": "readme.readme"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "about.data"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "spaces.rows", "from": "workspaces"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "readme.reload", "refresh": True},
        {"on": "about.reload", "refresh": True},
        # 作業空間を開く：同じ窓の「作業空間」のタブで出す
        {"on": "open_here.pressed", "open": "frame-workspace", "args": {"module": {"arg": "module"}, "space": {"arg": "module"}}, "here": True},
        {"on": "spaces.action", "when": {"action": "open"}, "open": "frame-workspace",
         "args": {"module": {"arg": "module"}, "space": {"payload": "id"}}, "here": True},
        # 「このモジュール」から：依存関係（C++ の画面）・タスク管理（同じ窓で切り替える）
        {"on": "about.opened", "when": {"page": "deps"}, "open": "cpp-deps", "args": {"module": {"arg": "module"}}, "here": True},
        {"on": "about.opened", "when": {"page": "tasks"}, "open": "tasks", "args": {"module": {"arg": "module"}}, "here": True},
    ],
}
