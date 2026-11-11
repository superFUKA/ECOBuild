"""モジュール › Project › 追加：入力の窓。名前・種類・リンクするライブラリを決めて、Project を足す（ecobuild project add）。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "Projectを追加", "width": 600, "height": 560},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "Projectを追加", "ok": "追加", "initial": {"place": {"arg": "module"}},
            "fields": [
                {"name": "name", "label": "名前（ディレクトリ名にもなる）", "required": True, "row": "project"},
                {"name": "kind", "label": "種類", "type": "select", "value": "app", "row": "project", "options": [
                    {"value": "library", "label": "ライブラリ（静的 .lib）"}, {"value": "shared", "label": "ライブラリ（共有 .dll）"},
                    {"value": "app", "label": "実行ファイル"}, {"value": "test", "label": "テスト"}, {"value": "bench", "label": "性能測定"}]},
                {"name": "link", "label": "リンクするライブラリ", "type": "select", "show_if": {"kind": ["app", "test", "bench"]}, "none_label": "なし",
                 "options_from": {"source": "rows", "value": "name", "label": "name", "note": "kind", "note_labels": {
                     "static_library": "ライブラリ", "shared_library": "共有ライブラリ", "library": "ライブラリ", "executable": "実行ファイル",
                     "test": "テスト", "benchmark": "性能測定", "bench": "性能測定"}},
                 "help": "テスト・性能測定にはライブラリが必要です（このモジュールのライブラリの Project を選びます）。"},
                {"name": "test", "label": "組のテスト用Project（名前Test）も作る", "type": "checkbox", "value": True, "inverse": "no_test",
                 "show_if": {"kind": ["library", "shared"]}},
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "project list", "args": {"module": {"arg": "module"}}, "to": "form.rows"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        # 人が打つのと同じ：（作業空間で）ecobuild project add <名前> --kind <種類> [--link <ライブラリ>] [--no-test]
        {"on": "form.submitted", "run": "project add", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "name": {"payload": "values.name"}, "kind": {"payload": "values.kind"},
                  "link": {"payload": "values.link"}, "no_test": {"payload": "values.no_test"}},
         "notify": "Projectを追加しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
