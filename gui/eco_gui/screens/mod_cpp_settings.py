"""モジュール › 全般 › 変更：入力の窓。モジュールの設定を変える（ecobuild module settings set [--main <Project>] [--no-main]
[--msvc-runtime <dll|static>] [--projects-folder …] [--linked-folder …] [--external-folder …]）。
"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "モジュールの設定", "width": 640, "height": 620},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "モジュールの設定", "ok": "保存", "initial": {"place": {"arg": "module"}},
            "fields": [
                {"name": "main", "label": "他のモジュールからリンクされるProject（main）", "type": "select", "value_from": "main_project",
                 "none_label": "（変えない）",
                 "options_from": {"source": "rows", "value": "name", "label": "name", "note": "kind", "note_labels": {
                     "static_library": "ライブラリ", "shared_library": "共有ライブラリ", "library": "ライブラリ", "executable": "実行ファイル",
                     "test": "テスト", "benchmark": "性能測定", "bench": "性能測定"}},
                 "help": "ライブラリのProjectだけを選べます。", "hide_if": {"no_main": True}},
                {"name": "no_main", "label": "main をなしにする（他のモジュールからリンクできない）", "type": "checkbox"},
                {"name": "msvc_runtime", "label": "MSVC のCランタイム（このモジュールを頂点にしたビルド全体）", "type": "radio", "inline": True, "options": [
                    {"value": "dll", "label": "DLL（/MD）"}, {"value": "static", "label": "静的（/MT）"}]},
                {"type": "section", "label": "Visual Studio のソリューションフォルダー"},
                {"name": "projects_folder", "label": "自分のProject", "row": "f1", "value_from": "folders.projects"},
                {"name": "linked_folder", "label": "リンク先のモジュール", "row": "f1", "value_from": "folders.linked_projects"},
                {"name": "external_folder", "label": "CMake・GoogleTest 等", "value_from": "folders.external"},
                {"type": "section", "end": True},
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "module settings", "args": {"module": {"arg": "module"}}, "to": "form.values"},
        {"read": "project list", "args": {"module": {"arg": "module"}}, "to": "form.rows"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        {"on": "form.submitted", "run": "module settings set", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "main": {"payload": "values.main"}, "no_main": {"payload": "values.no_main"},
                  "msvc_runtime": {"payload": "values.msvc_runtime"}, "projects_folder": {"payload": "values.projects_folder"},
                  "linked_folder": {"payload": "values.linked_folder"}, "external_folder": {"payload": "values.external_folder"}},
         "notify": "モジュールの設定を保存しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
