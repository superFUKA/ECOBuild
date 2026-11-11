"""モジュール › Project › リンクを外す：入力の窓。Project のリンクを1つ選んで外す（ecobuild project unlink <リンク> --project <名前>）。

依存先のモジュールを丸ごと外すには、「依存先」の「リンクを外す…」を使う。
"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・リンクを外す Project

SCREEN = {
    "root": "page",
    "window": {"title": "リンクを外す", "width": 600, "height": 420},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "リンクを外す", "subject": {"arg": "name"}, "ok": "外す", "danger": True, "initial": {"place": {"arg": "module"}},
            "intro": "依存先のモジュールを丸ごと外すには「依存先」タブの「リンクを外す…」を使います。",
            "fields": [
                {"name": "link", "label": "外すリンク", "type": "select", "required": True, "empty_text": "リンクはありません。",
                 "options_from": {"source": "rows", "value": "id", "label": "name", "note": ["kind", "as"], "note_labels": {
                     "project": "このモジュール", "library": "このモジュール", "module": "依存先のモジュール", "package": "CMakeのパッケージ",
                     "cmake": "CMakeのソース", "file": "ビルド済みのファイル", "static": "静的", "shared": "共有", "interface": "インターフェース"}}},
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "project show", "args": {"module": {"arg": "module"}, "project": {"arg": "name"}}, "require": ["project"], "to": "form.rows", "from": "links"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        {"on": "form.submitted", "run": "project unlink", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "link": {"payload": "values.link"}, "project": {"arg": "name"}},
         "notify": "リンクを外しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
