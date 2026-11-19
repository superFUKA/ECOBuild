"""モジュール › 依存先 › リンク：入力の窓。ほかのモジュール（GitHub のリポジトリ）を依存先としてリンクする
（ecobuild deps add <リポジトリ> [--project <Project>] [--library <相手のライブラリ>] [--shared] [--at <版>]）。

相手のどのライブラリにリンクするかは、「ライブラリを読む」で一覧（ecobuild deps libraries <リポジトリ> [--at <版>]）を読んで選ぶ
（選ばなければ相手の main）。同じ依存先の別のライブラリにも、もう一度この窓でリンクを足せる。
"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "モジュールをリンク", "width": 640, "height": 560},
    "nodes": [
        {"id": "page", "part": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "モジュールをリンク", "ok": "リンク", "initial": {"place": {"arg": "module"}},
            "actions": [{"name": "libraries", "label": "ライブラリを読む", "hint": "リポジトリ（と版）の、リンクできるライブラリの一覧を読みます"}],
            "fields": [
                {"name": "repository", "label": "リポジトリ（名前、または 所有者/名前）", "required": True, "placeholder": "例：owner/Math"},
                {"name": "project", "label": "リンクするProject", "type": "select", "none_label": "既定（テスト用を除いて1つならそれ）",
                 "options_from": {"source": "rows", "value": "name", "label": "name", "note": "kind", "note_labels": {
                     "static_library": "ライブラリ", "shared_library": "共有ライブラリ", "library": "ライブラリ", "executable": "実行ファイル",
                     "test": "テスト", "benchmark": "性能測定", "bench": "性能測定"}},
                 "help": "このモジュールの、リンクを足す側の Project です。"},
                {"name": "library", "label": "相手のライブラリ", "type": "select", "none_label": "既定（相手の main）",
                 "options_from": {"source": "choices", "value": "name", "label": "name", "note": "kind", "where": {"linkable": True},
                                  "note_labels": {
                     "static_library": "静的ライブラリ", "shared_library": "共有ライブラリ", "interface_library": "ヘッダーだけのライブラリ"}},
                 "help": "「ライブラリを読む」で、リポジトリ（と版）のライブラリの一覧を読みます。読まなければ相手の main にリンクします。"},
                {"name": "shared", "label": "共有ライブラリとしてリンクする", "type": "checkbox"},
                {"name": "at", "label": "版（任意）", "placeholder": "空なら既定のブランチの最新",
                 "help": "ブランチ・タグ・コミットを指定できます。後から行の「版を選ぶ…」で選び直せます。"},
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "project list", "args": {"module": {"arg": "module"}}, "to": "form.rows"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        # 「ライブラリを読む」：相手のライブラリの一覧（読むだけ。まだ依存先でなければ GitHub から一時的に取る）
        {"on": "form.action", "when": {"name": "libraries"}, "run": "deps libraries", "require": ["target"],
         "args": {"module": {"arg": "module"}, "target": {"payload": "values.repository"}, "at": {"payload": "values.at"}},
         "set": {"dep_libraries": {"result": "libraries"}, "dep_problem": None}, "failed": {"dep_problem": {"error": "message"}}},
        {"value": "dep_libraries", "to": "form.choices"},
        {"value": "dep_problem", "to": "form.problem"},
        {"on": "form.submitted", "run": "deps add", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "repository": {"payload": "values.repository"}, "project": {"payload": "values.project"},
                  "library": {"payload": "values.library"}, "shared": {"payload": "values.shared"}, "at": {"payload": "values.at"}},
         "notify": "{name} をリンクしました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
