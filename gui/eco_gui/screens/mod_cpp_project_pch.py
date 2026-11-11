"""モジュール › Project › PCH：入力の窓。プリコンパイル済みヘッダーを使う・入れるヘッダーを決める・使わない
（ecobuild project pch --project <名前> [--header …] [--system …] [--off]）。
"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・設定する Project

SCREEN = {
    "root": "page",
    "window": {"title": "プリコンパイル済みヘッダー", "width": 640, "height": 520},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "プリコンパイル済みヘッダー", "subject": {"arg": "name"}, "ok": "保存", "initial": {"place": {"arg": "module"}},
            "intro": "ヘッダーを書かなければ、include/{name}/pch.h を作って使います。", "vars": {"name": {"arg": "name"}},
            "fields": [
                {"name": "off", "label": "PCH を使わない", "type": "checkbox"},
                {"name": "header", "label": "Projectのヘッダー（Projectからの相対、カンマ区切り）", "value_from": "pch.headers",
                 "placeholder": "例：include/{name}/common.h", "hide_if": {"off": True}},
                {"name": "system", "label": "標準・外部のヘッダー（<> で読むもの、カンマ区切り）", "value_from": "pch.system_headers",
                 "placeholder": "例：vector, string, memory", "hide_if": {"off": True}},
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "project show", "args": {"module": {"arg": "module"}, "project": {"arg": "name"}}, "require": ["project"], "to": "form.values"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        {"on": "form.submitted", "run": "project pch", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "project": {"arg": "name"}, "off": {"payload": "values.off"},
                  "header": {"payload": "values.header"}, "system": {"payload": "values.system"}},
         "notify": "PCHの設定を変更しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
