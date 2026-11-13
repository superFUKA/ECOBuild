"""モジュール › 依存先：C++ のモジュールの依存先の状態と依存関係の図。足す・更新・版を選ぶ・外す。

部品 mod-cpp が表を描く。変える操作は、入力の窓（mod-cpp-…：共通の部品 form）を重ねて開く。管理ファイル（ecobuild.toml・CMake）が
変わる操作は、窓の中で選んだタスクブランチの作業空間で実行する。同じコマンドの読みは1回だけ実行され、いくつもの要る情報へ出る。
"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "モジュール", "width": 1280, "height": 820, "refresh": {"focus": True}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "section", "deps"]},
        {"id": "nav", "screen": "menu", "args": {"current": "overview", "module": {"arg": "module"}}},
        {"id": "section", "screen": "mod-tabs", "args": {"current": "cpp-deps", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "head_tools"]},
        {"id": "head_tools", "layout": "row", "look": "tools", "children": ["update", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "モジュール", "heading": True}},
        {"id": "update", "part": "button", "props": {"label": "構成を今のファイルに合わせる", "quiet": True, "hint": "Visual Studio のソリューション等を作り直す（ビルドはしない。ecobuild project update）"}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        {"id": "deps", "part": "mod-cpp", "props": {"view": "deps"}},
    ],
    "bindings": [
        {"on": "reload.pressed", "refresh": True},
        {"on": "update.pressed", "run": "project update", "args": {"module": {"arg": "module"}}, "notify": "構成を、今のファイルに合わせました。"},
        {"on": "deps.reload", "refresh": True},
        {"read": "project list", "args": {"module": {"arg": "module"}}, "to": "deps.projects"},
        {"read": "deps list", "args": {"module": {"arg": "module"}, "fetch": {"value": "cpp_fetch"}}, "to": "deps.deps"},
        {"read": "deps tree", "args": {"module": {"arg": "module"}}, "to": "deps.tree"},
        {"value": "cpp_fetch", "to": "deps.fetched"},
        {"value": "cpp_versions", "to": "deps.versions"},
        {"on": "deps.action", "when": {"name": "deps_fetch"}, "set": {"cpp_fetch": True}},
        {"on": "deps.action", "when": {"name": "deps_fetch"}, "refresh": True},
        {"on": "deps.action", "when": {"name": "deps_sync"}, "open": "mod-cpp-dep-sync", "inside": True, "args": {"module": {"arg": "module"}}},
        {"on": "deps.action", "when": {"name": ["deps_update", "dep_update"]}, "open": "mod-cpp-dep-update", "inside": True, "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},
        {"on": "deps.action", "when": {"name": "dep_add"}, "open": "mod-cpp-dep-add", "inside": True, "args": {"module": {"arg": "module"}}},
        {"on": "deps.action", "when": {"name": "dep_remove"}, "open": "mod-cpp-dep-remove", "inside": True, "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},
        {"on": "deps.action", "when": {"name": "dep_versions"}, "run": "deps versions", "args": {"module": {"arg": "module"}, "name": {"payload": "target"}, "branch": {"payload": "value"}}, "set": {"cpp_versions": {"result": ""}}},
        {"on": "deps.action", "when": {"name": "dep_versions_close"}, "set": {"cpp_versions": None}},
        {"on": "deps.action", "when": {"name": "dep_use"}, "open": "mod-cpp-dep-update", "inside": True, "args": {"module": {"arg": "module"}, "name": {"payload": "target"}, "at": {"payload": "value"}}},
    ],
}
