"""モジュール › C++：サブプロジェクト（Project）・依存先・ファイルテンプレート。C++ のモジュールでだけ使える。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "C++", "width": 940, "height": 720},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "head", "tabs"]},
        {"id": "nav", "screen": "menu", "args": {"current": "cpp", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload", "to_files"]},
        {"id": "title", "part": "note", "props": {"text": "C++ のサブプロジェクト", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "to_files", "part": "button", "props": {"label": "ファイルへ戻る"}},
        {"id": "tabs", "layout": "tabs", "props": {"labels": ["サブプロジェクト", "依存先", "テンプレート"]},
         "children": ["projects_tab", "deps_tab", "templates_tab"]},

        # サブプロジェクト（ecobuild project list・add・move・remove・update、ecobuild module settings）
        {"id": "projects_tab", "layout": "column", "children": ["settings", "projects", "project_chosen", "project_move", "project_new", "update"]},
        {"id": "settings", "part": "facts", "props": {"items": [
            {"key": "main_project", "label": "ほかのモジュールからリンクされるサブプロジェクト"}, {"key": "msvc_runtime", "label": "MSVC の C ランタイム"}],
            "labels": {"msvc_runtime": {"dll": "DLL（/MD）", "static": "静的（/MT）"}}}},
        {"id": "projects", "part": "table", "props": {
            "columns": [{"key": "name", "label": "名前"}, {"key": "kind", "label": "種類"}, {"key": "directory", "label": "場所"},
                        {"key": "links", "label": "リンク"}],
            "key": "name",
            "labels": {"kind": {"library": "静的ライブラリ", "static_library": "静的ライブラリ", "shared": "共有ライブラリ",
                                "shared_library": "共有ライブラリ", "interface": "ヘッダーだけ", "app": "実行ファイル",
                                "executable": "実行ファイル", "test": "テスト", "bench": "性能測定", "benchmark": "性能測定"}},
            "actions": [{"name": "choose", "label": "選ぶ"}, {"name": "remove", "label": "外す"}],
            "empty_text": "サブプロジェクトはありません。",
        }},
        {"id": "project_chosen", "part": "note", "props": {"prefix": "選んでいるサブプロジェクト："}},
        {"id": "project_move", "layout": "row", "children": ["project_destination", "do_project_move"]},
        {"id": "project_destination", "part": "text-input", "props": {"title": "選んだサブプロジェクトの移動先（まだないフォルダー）", "placeholder": "例：libs/Math"}},
        {"id": "do_project_move", "part": "button", "props": {"label": "移す"}},
        {"id": "project_new", "layout": "row", "children": ["project_name", "project_kind", "do_project_add"]},
        {"id": "project_name", "part": "text-input", "props": {"title": "新しいサブプロジェクトの名前", "placeholder": "例：Math"}},
        {"id": "project_kind", "part": "select", "props": {"title": "種類", "options": [
            {"value": "", "label": "（既定）"}, {"value": "library", "label": "静的ライブラリ"}, {"value": "shared", "label": "共有ライブラリ"},
            {"value": "app", "label": "実行ファイル"}, {"value": "test", "label": "テスト"}, {"value": "bench", "label": "性能測定"}]}},
        {"id": "do_project_add", "part": "button", "props": {"label": "＋ 足す", "primary": True}},
        {"id": "update", "part": "button", "props": {"label": "構成を今のファイルに合わせる", "hint": "Visual Studio のソリューション等を作り直す（ビルドはしない）"}},

        # 依存先（ecobuild deps list・add・remove・update・sync）
        {"id": "deps_tab", "layout": "column", "children": ["deps", "deps_all", "dep_new"]},
        {"id": "deps", "part": "table", "props": {
            "columns": [{"key": "name", "label": "名前"}, {"key": "state", "label": "状態"}, {"key": "recorded", "label": "記録の版"},
                        {"key": "local", "label": "手元の版"}, {"key": "url", "label": "場所"}],
            "key": "name",
            "labels": {"state": {"aligned": "記録の版", "differs": "記録と別の版", "modified": "未コミットの変更あり",
                                 "working": "作業版", "missing": "clone なし"}},
            "actions": [{"name": "update", "label": "最新にする"}, {"name": "remove", "label": "外す"}],
            "empty_text": "依存先はありません。",
        }},
        {"id": "deps_all", "layout": "row", "children": ["deps_sync", "deps_update"]},
        {"id": "deps_sync", "part": "button", "props": {"label": "手元を記録の版に合わせる", "hint": "ecobuild deps sync"}},
        {"id": "deps_update", "part": "button", "props": {"label": "全部を最新にする", "hint": "ecobuild deps update"}},
        {"id": "dep_new", "layout": "row", "children": ["dep_repository", "dep_at", "do_dep_add"]},
        {"id": "dep_repository", "part": "text-input", "props": {"title": "足す依存先（GitHub のリポジトリ）", "placeholder": "例：owner/Math"}},
        {"id": "dep_at", "part": "text-input", "props": {"title": "版（空なら最新）", "placeholder": "例：v1.2.0"}},
        {"id": "do_dep_add", "part": "button", "props": {"label": "＋ 足す", "primary": True}},

        # ファイルテンプレート（ecobuild template list・add・remove）
        {"id": "templates_tab", "layout": "column", "children": ["templates", "template_new"]},
        {"id": "templates", "part": "named-table", "props": {
            "columns": [{"key": "path", "label": "元のファイル"}, {"key": "builtin", "label": "種類"}],
            "name_label": "テンプレート", "labels": {"builtin": {"true": "ECOBuild の既定", "false": "このモジュール"}},
            "actions": [{"name": "remove", "label": "外す"}],
            "empty_text": "テンプレートはありません。",
        }},
        {"id": "template_new", "layout": "row", "children": ["template_name", "template_source", "do_template_add"]},
        {"id": "template_name", "part": "text-input", "props": {"title": "新しいテンプレートの名前", "placeholder": "例：widget"}},
        {"id": "template_source", "part": "text-input", "props": {"title": "元にするファイル", "placeholder": "例：templates/widget.h"}},
        {"id": "do_template_add", "part": "button", "props": {"label": "＋ 足す", "primary": True}},
    ],
    "bindings": [
        {"on": "reload.pressed", "refresh": True},
        {"on": "to_files.pressed", "open": "files", "args": {"module": {"arg": "module"}}, "here": True},
        # サブプロジェクト
        {"read": "module settings", "args": {"module": {"arg": "module"}}, "to": "settings.data"},
        {"read": "project list", "args": {"module": {"arg": "module"}}, "to": "projects.rows"},
        {"on": "projects.action", "when": {"action": "choose"}, "set": {"cpp_project": {"payload": "id"}}},
        {"value": "cpp_project", "to": "project_chosen.text"},
        {"on": "projects.action", "when": {"action": "remove"}, "run": "project remove",
         "args": {"module": {"arg": "module"}, "name": {"payload": "id"}}, "set": {"cpp_project": None}},
        {"on": "project_destination.changed", "set": {"cpp_project_destination": {"payload": "text"}}},
        {"on": "do_project_move.pressed", "run": "project move",
         "args": {"module": {"arg": "module"}, "name": {"value": "cpp_project"}, "destination": {"value": "cpp_project_destination"}}},
        {"on": "project_name.changed", "set": {"cpp_project_name": {"payload": "text"}}},
        {"on": "project_kind.changed", "set": {"cpp_project_kind": {"payload": "value"}}},
        {"value": "cpp_project_kind", "to": "project_kind.value"},
        {"on": "do_project_add.pressed", "run": "project add",
         "args": {"module": {"arg": "module"}, "name": {"value": "cpp_project_name"}, "kind": {"value": "cpp_project_kind"}}},
        {"on": "update.pressed", "run": "project update", "args": {"module": {"arg": "module"}}},
        # 依存先
        {"read": "deps list", "args": {"module": {"arg": "module"}}, "to": "deps.rows"},
        {"on": "deps.action", "when": {"action": "update"}, "run": "deps update", "args": {"module": {"arg": "module"}, "name": {"payload": "id"}}},
        {"on": "deps.action", "when": {"action": "remove"}, "run": "deps remove", "args": {"module": {"arg": "module"}, "name": {"payload": "id"}}},
        {"on": "deps_sync.pressed", "run": "deps sync", "args": {"module": {"arg": "module"}}},
        {"on": "deps_update.pressed", "run": "deps update", "args": {"module": {"arg": "module"}}},
        {"on": "dep_repository.changed", "set": {"cpp_dep_repository": {"payload": "text"}}},
        {"on": "dep_at.changed", "set": {"cpp_dep_at": {"payload": "text"}}},
        {"on": "do_dep_add.pressed", "run": "deps add",
         "args": {"module": {"arg": "module"}, "repository": {"value": "cpp_dep_repository"}, "at": {"value": "cpp_dep_at"}}},
        # テンプレート
        {"read": "template list", "args": {"module": {"arg": "module"}}, "to": "templates.entries"},
        {"on": "templates.action", "when": {"action": "remove"}, "run": "template remove", "args": {"module": {"arg": "module"}, "name": {"payload": "id"}}},
        {"on": "template_name.changed", "set": {"cpp_template_name": {"payload": "text"}}},
        {"on": "template_source.changed", "set": {"cpp_template_source": {"payload": "text"}}},
        {"on": "do_template_add.pressed", "run": "template add",
         "args": {"module": {"arg": "module"}, "name": {"value": "cpp_template_name"}, "source": {"value": "cpp_template_source"}}},
    ],
}
