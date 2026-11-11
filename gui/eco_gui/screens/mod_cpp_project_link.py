"""モジュール › Project › リンク：入力の窓。Project に、このモジュールのライブラリ・CMake のパッケージ／ソース・ビルド済みのファイルをリンクする
（ecobuild project link --project <名前> …）。ほかのモジュール（GitHub のリポジトリ）は、「依存先」の「＋ リンク」で足す。
"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・リンクを足す Project

SCREEN = {
    "root": "page",
    "window": {"title": "リンク", "width": 680, "height": 700},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "リンクを足す", "subject": {"arg": "name"}, "ok": "保存", "initial": {"place": {"arg": "module"}},
            "fields": [
                {"name": "what", "label": "リンクするもの", "type": "radio", "value": "project", "options": [
                    {"value": "project", "label": "このモジュールのライブラリ"},
                    {"value": "package", "label": "CMakeのパッケージ", "help": "find_package で見つけるもの（<名前>Config.cmake）"},
                    {"value": "cmake", "label": "CMakeのソース", "help": "add_subdirectory するフォルダー"},
                    {"value": "file", "label": "ビルド済みのファイル", "help": ".lib・.dll 等"}]},
                {"name": "library", "label": "ライブラリ", "type": "select", "show_if": {"what": "project"}, "none_label": "（選んでください）",
                 "options_from": {"source": "rows", "value": "name", "label": "name", "note": "kind", "note_labels": {
                     "static_library": "ライブラリ", "shared_library": "共有ライブラリ", "library": "ライブラリ", "executable": "実行ファイル",
                     "test": "テスト", "benchmark": "性能測定", "bench": "性能測定"}}},
                {"name": "type", "label": "形式", "type": "select", "value": "", "show_if": {"what": ["project", "file"]}, "options": [
                    {"value": "", "label": "相手の作成時の形式（このモジュールのライブラリ）"}, {"value": "static", "label": "静的"},
                    {"value": "shared", "label": "共有"}, {"value": "interface", "label": "インターフェース（ヘッダーだけ）"}],
                 "help": "ビルド済みのファイルは、静的・共有・インターフェースのどれかを選びます。"},
                {"name": "package", "label": "パッケージ名", "row": "pkg", "placeholder": "例：fmt", "show_if": {"what": "package"}},
                {"name": "directory", "label": "Config.cmake のあるディレクトリ（Projectからの相対）", "row": "pkg", "show_if": {"what": "package"}},
                {"name": "cmake", "label": "CMakeのソースのディレクトリ（Projectからの相対）", "show_if": {"what": "cmake"}},
                {"name": "target", "label": "CMakeのターゲット", "placeholder": "例：fmt::fmt", "show_if": {"what": ["package", "cmake"]}},
                {"name": "file", "label": "ファイル（構成=パス、カンマ区切り）", "placeholder": "Debug=lib/foo_d.lib, Release=lib/foo.lib",
                 "show_if": {"what": "file"}},
                {"name": "implib", "label": "共有ライブラリのインポートライブラリ（構成=パス、カンマ区切り）", "show_if": {"what": "file", "type": "shared"}},
                {"name": "include", "label": "インクルードディレクトリ（Projectからの相対、カンマ区切り）", "show_if": {"what": "file"}},
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "project list", "args": {"module": {"arg": "module"}}, "to": "form.rows"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        # 人が打つのと同じ：（作業空間で）ecobuild project link --project <名前> [<ライブラリ> --type <形式>]
        # [--package <名前> --directory <場所> --target <ターゲット>] [--cmake <場所> --target …] [--type <形式> --file … --implib … --include …]
        {"on": "form.submitted", "run": "project link", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "project": {"arg": "name"}, "library": [{"payload": "values.library"}],
                  "type": {"payload": "values.type"},
                  "package": {"payload": "values.package"}, "directory": {"payload": "values.directory"}, "cmake": {"payload": "values.cmake"},
                  "target": {"payload": "values.target"}, "file": {"payload": "values.file"}, "implib": {"payload": "values.implib"},
                  "include": {"payload": "values.include"}},
         "notify": "リンクを変更しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
