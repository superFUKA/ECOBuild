"""モジュール › Project・依存先：C++ のモジュールの Project・依存先・全般（モジュールの設定）・ファイルテンプレート。C++ のモジュールでだけ使える。

どのタブも、部品 mod-cpp が表を描く（今の GUI と同じ：Project の木と種類の印、依存先の状態の色と依存関係の図、設定の表、テンプレート）。
変える操作は、入力の窓（mod-cpp-…：共通の部品 form）を重ねて開く。管理ファイル（ecobuild.toml・CMake）が変わる操作は、
窓の中で選んだタスクブランチの作業空間で実行する。
"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "Project・依存先", "width": 1280, "height": 820, "refresh": {"focus": True}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "tabs"]},
        {"id": "nav", "screen": "menu", "args": {"current": "overview", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "head_tools"]},
        {"id": "head_tools", "layout": "row", "look": "tools", "children": ["back", "update", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "Project・依存先", "heading": True}},
        {"id": "back", "part": "button", "props": {"label": "← 概要", "quiet": True, "hint": "概要へ戻る"}},
        {"id": "update", "part": "button", "props": {
            "label": "構成を今のファイルに合わせる", "quiet": True, "hint": "Visual Studio のソリューション等を作り直す（ビルドはしない。ecobuild project update）"}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        {"id": "tabs", "layout": "tabs", "props": {"labels": ["Project", "依存先", "全般", "テンプレート"]},
         "children": ["projects", "deps", "general", "templates"]},
        {"id": "projects", "part": "mod-cpp", "props": {"view": "projects"}},
        {"id": "deps", "part": "mod-cpp", "props": {"view": "deps"}},
        {"id": "general", "part": "mod-cpp", "props": {"view": "general"}},
        {"id": "templates", "part": "mod-cpp", "props": {"view": "templates"}},
    ],
    "bindings": [
        {"on": "reload.pressed", "refresh": True},
        {"on": "back.pressed", "open": "overview", "args": {"module": {"arg": "module"}}, "here": True},
        {"on": "update.pressed", "run": "project update", "args": {"module": {"arg": "module"}}, "notify": "構成を、今のファイルに合わせました。"},
        {"on": "projects.reload", "refresh": True},
        {"on": "deps.reload", "refresh": True},
        {"on": "general.reload", "refresh": True},
        {"on": "templates.reload", "refresh": True},
        # 読む（同じコマンドは1回だけ実行され、いくつもの部品へ出る）。依存先は、「GitHubと照らし合わせる」を押した後は --fetch で読む
        {"read": "project list", "args": {"module": {"arg": "module"}}, "to": "projects.projects"},
        {"read": "project list", "args": {"module": {"arg": "module"}}, "to": "deps.projects"},
        {"read": "deps list", "args": {"module": {"arg": "module"}, "fetch": {"value": "cpp_fetch"}}, "to": "projects.deps"},
        {"read": "deps list", "args": {"module": {"arg": "module"}, "fetch": {"value": "cpp_fetch"}}, "to": "deps.deps"},
        {"read": "deps tree", "args": {"module": {"arg": "module"}}, "to": "deps.tree"},
        {"read": "module settings", "args": {"module": {"arg": "module"}}, "to": "projects.settings"},
        {"read": "module settings", "args": {"module": {"arg": "module"}}, "to": "general.settings"},
        {"read": "module settings", "args": {"module": {"arg": "module"}}, "to": "templates.settings"},
        {"value": "cpp_fetch", "to": "deps.fetched"},
        {"value": "cpp_versions", "to": "deps.versions"},

        # --- Project（ecobuild project add・set・link・unlink・pch・move・remove）：入力の窓 ---
        {"on": "projects.action", "when": {"name": "project_add"}, "open": "mod-cpp-project-add", "inside": True, "args": {"module": {"arg": "module"}}},
        {"on": "projects.action", "when": {"name": "project_settings"}, "open": "mod-cpp-project-settings", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},
        {"on": "projects.action", "when": {"name": "project_link"}, "open": "mod-cpp-project-link", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},
        {"on": "projects.action", "when": {"name": "project_unlink"}, "open": "mod-cpp-project-unlink", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},
        {"on": "projects.action", "when": {"name": "project_pch"}, "open": "mod-cpp-project-pch", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},
        {"on": "projects.action", "when": {"name": "project_move"}, "open": "mod-cpp-project-move", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},
        {"on": "projects.action", "when": {"name": "project_remove"}, "open": "mod-cpp-project-remove", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},

        # --- 依存先（ecobuild deps list --fetch・sync・update・add・remove・versions） ---
        {"on": "deps.action", "when": {"name": "deps_fetch"}, "set": {"cpp_fetch": True}},
        {"on": "deps.action", "when": {"name": "deps_fetch"}, "refresh": True},
        {"on": "deps.action", "when": {"name": "deps_sync"}, "open": "mod-cpp-dep-sync", "inside": True, "args": {"module": {"arg": "module"}}},
        {"on": "deps.action", "when": {"name": ["deps_update", "dep_update"]}, "open": "mod-cpp-dep-update", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},
        {"on": "deps.action", "when": {"name": "dep_add"}, "open": "mod-cpp-dep-add", "inside": True, "args": {"module": {"arg": "module"}}},
        {"on": "deps.action", "when": {"name": "dep_remove"}, "open": "mod-cpp-dep-remove", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},
        # 版を選ぶ：選べる版（ecobuild deps versions <名前> [--branch <ブランチ>]：GitHub から取り込み直して読むので、押したときに実行し、
        # 結果を共有の値へ）→ 選んだ版を記録する入力の窓（ecobuild deps update --name <名前> --at <版>）
        {"on": "deps.action", "when": {"name": "dep_versions"}, "run": "deps versions",
         "args": {"module": {"arg": "module"}, "name": {"payload": "target"}, "branch": {"payload": "value"}}, "set": {"cpp_versions": {"result": ""}}},
        {"on": "deps.action", "when": {"name": "dep_versions_close"}, "set": {"cpp_versions": None}},
        {"on": "deps.action", "when": {"name": "dep_use"}, "open": "mod-cpp-dep-update", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"payload": "target"}, "at": {"payload": "value"}}},

        # --- 全般（ecobuild module settings …）・テンプレート（ecobuild template add・remove） ---
        {"on": "general.action", "when": {"name": "module_settings"}, "open": "mod-cpp-settings", "inside": True, "args": {"module": {"arg": "module"}}},
        {"on": "templates.action", "when": {"name": "template_add"}, "open": "mod-cpp-template-add", "inside": True, "args": {"module": {"arg": "module"}}},
        {"on": "templates.action", "when": {"name": "template_replace"}, "open": "mod-cpp-template-add", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},
        {"on": "templates.action", "when": {"name": "template_remove"}, "open": "mod-cpp-template-remove", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"payload": "target"}}},
    ],
}
