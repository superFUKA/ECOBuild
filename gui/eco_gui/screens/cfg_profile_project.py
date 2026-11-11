"""ビルド設定の、Project ごとの上書き（入力の窓）：C++ のモジュール。ライブラリの形式・C++ の規格など。"""

ARGS = {"module": ".", "name": "", "project": ""}  # モジュールのフォルダー・ビルド設定の名前・変える Project（新しく足すなら空）

SCREEN = {
    "root": "page",
    "window": {"title": "Projectごとの上書き", "width": 640, "height": 640},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "Projectごとの上書き", "ok": "保存",
            "intro": "指定した項目で置き換えます（空にした項目は上書きしません）。構成・生成器・アーキテクチャはモジュール全体で1つです。",
            "at": [{"arg": "name"}, "projects", {"arg": "project"}],
            "fields": [
                {"name": "project", "label": "Project", "type": "select", "required": True, "value": {"arg": "project"},
                 "options_from": {"value": "name", "label": "name", "note": "kind"}},
                {"name": "type", "label": "ライブラリの形式（使う側のリンクもこの形式になる）", "type": "select", "value": "", "options": [
                    {"value": "", "label": "上書きしない"}, {"value": "static", "label": "静的"}, {"value": "shared", "label": "共有"},
                    {"value": "interface", "label": "インターフェース"}]},
                {"name": "cpp_standard", "label": "C++の規格", "type": "select", "value": "", "options": [
                    {"value": "", "label": "上書きしない"}, {"value": "17", "label": "C++17"}, {"value": "20", "label": "C++20"}, {"value": "23", "label": "C++23"}]},
                {"name": "artifact_directory", "label": "成果物の置き場所（ビルドツリーからの相対）"},
                {"name": "test_parallel", "label": "テストを並列に実行する数（テスト用Project）", "type": "number", "min": 1},
                {"name": "googletest_archive", "label": "GoogleTestのZIP（テスト用Project）"},
            ],
        }},
    ],
    "bindings": [
        {"read": "profile list", "args": {"module": {"arg": "module"}}, "to": "form.values", "from": "profiles"},
        {"read": "project list", "args": {"module": {"arg": "module"}}, "to": "form.rows"},
        {"on": "form.cancelled", "close": True},
        # ecobuild profile project <ビルド設定> <Project> [--type …] [--cpp-standard …] …
        {"on": "form.submitted", "run": "profile project",
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "project": {"payload": "values.project"},
                  "type": {"payload": "values.type"}, "cpp_standard": {"payload": "values.cpp_standard"},
                  "artifact_directory": {"payload": "values.artifact_directory"}, "test_parallel": {"payload": "values.test_parallel"},
                  "googletest_archive": {"payload": "values.googletest_archive"}},
         "notify": "上書きを保存しました。", "close": True},
    ],
}
