"""モジュール › Project：C++ のモジュールの Project の木と種類の印。足す・設定・リンク・移す・消す。

部品 mod-cpp が表を描く。変える操作は、入力の窓（mod-cpp-…：共通の部品 form）を重ねて開く。管理ファイル（ecobuild.toml・CMake）が
変わる操作は、窓の中で選んだタスクブランチの作業空間で実行する。同じコマンドの読みは1回だけ実行され、いくつもの要る情報へ出る。
"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "モジュール", "width": 1360, "height": 880, "refresh": {"focus": True}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "section", "projects"]},
        {"id": "nav", "screen": "menu", "args": {"current": "overview", "module": {"arg": "module"}}},
        {"id": "section", "screen": "mod-tabs", "args": {"current": "cpp", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "shown", "head_tools"]},
        {"id": "head_tools", "layout": "row", "look": "tools", "children": ["update", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "モジュール", "heading": True}},
        {"id": "shown", "part": "mod-shown-place"},
        {"id": "update", "part": "button", "props": {"label": "構成を今のファイルに合わせる", "quiet": True, "hint": "Visual Studio のソリューション等を作り直す（ビルドはしない。ecobuild project update）"}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        {"id": "projects", "part": "mod-cpp", "props": {"view": "projects"}},
    ],
    "bindings": [
        # 「表示」：どの場所の中身で見るか（モジュールのフォルダー＝既定のブランチ／作業空間）。選んだ場所は共有の値 place
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "shown.workspaces", "from": "workspaces"},
        {"value": "place", "to": "shown.value"},
        {"on": "shown.changed", "set": {"place": {"payload": "path"}}},
        {"on": "reload.pressed", "refresh": True},
        {"on": "update.pressed", "run": "project update", "args": {"module": {"value": "place", "else": {"arg": "module"}}}, "notify": "構成を、今のファイルに合わせました。"},
        {"on": "projects.reload", "refresh": True},
        # 作業空間がなければ、変える操作は灰色と「今は見るだけ」の帯（そこから、タスク管理を開く）
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "projects.workspaces", "from": "workspaces"},
        {"on": "projects.action", "when": {"name": "open_tasks"}, "open": "tasks", "args": {"module": {"arg": "module"}}, "here": True},
        {"read": "project list", "args": {"module": {"value": "place", "else": {"arg": "module"}}}, "to": "projects.projects"},
        {"read": "deps list", "args": {"module": {"value": "place", "else": {"arg": "module"}}, "fetch": {"value": "cpp_fetch"}}, "to": "projects.deps"},
        {"read": "module settings", "args": {"module": {"value": "place", "else": {"arg": "module"}}}, "to": "projects.settings"},
        {"on": "projects.action", "when": {"name": "project_add"}, "open": "mod-cpp-project-add", "inside": True, "args": {"module": {"value": "place", "else": {"arg": "module"}}}},
        {"on": "projects.action", "when": {"name": "project_settings"}, "open": "mod-cpp-project-settings", "inside": True, "args": {"module": {"value": "place", "else": {"arg": "module"}}, "name": {"payload": "target"}}},
        {"on": "projects.action", "when": {"name": "project_link"}, "open": "mod-cpp-project-link", "inside": True, "args": {"module": {"value": "place", "else": {"arg": "module"}}, "name": {"payload": "target"}}},
        {"on": "projects.action", "when": {"name": "project_unlink"}, "open": "mod-cpp-project-unlink", "inside": True, "args": {"module": {"value": "place", "else": {"arg": "module"}}, "name": {"payload": "target"}}},
        {"on": "projects.action", "when": {"name": "project_pch"}, "open": "mod-cpp-project-pch", "inside": True, "args": {"module": {"value": "place", "else": {"arg": "module"}}, "name": {"payload": "target"}}},
        {"on": "projects.action", "when": {"name": "project_move"}, "open": "mod-cpp-project-move", "inside": True, "args": {"module": {"value": "place", "else": {"arg": "module"}}, "name": {"payload": "target"}}},
        {"on": "projects.action", "when": {"name": "project_remove"}, "open": "mod-cpp-project-remove", "inside": True, "args": {"module": {"value": "place", "else": {"arg": "module"}}, "name": {"payload": "target"}}},
    ],
}
