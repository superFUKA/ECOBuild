"""ビルド設定を追加・編集（入力の窓）：名前と構成（型が C++・Python でないモジュール）。設定の画面から、窓の中に重ねて開く。"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・編集するビルド設定の名前（追加なら空）

SCREEN = {
    "root": "page",
    "window": {"title": "ビルド設定", "width": 560, "height": 420},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "cfg-form", "props": {
            "title": "ビルド設定", "ok": "保存",
            "intro": "同じ名前のビルド設定があれば置き換えます。ecobuild.toml が変わるので、タスクブランチでコミットしてください。",
            "at": [{"arg": "name"}],
            "fields": [
                {"name": "name", "label": "名前", "required": True, "value": {"arg": "name"}, "placeholder": "例：release"},
                {"name": "configuration", "label": "構成", "type": "select", "value": "Debug",
                 "options": [{"value": "Debug", "label": "Debug"}, {"value": "Release", "label": "Release"}]},
            ],
        }},
    ],
    "bindings": [
        {"read": "profile list", "args": {"module": {"arg": "module"}}, "to": "form.values", "from": "profiles"},
        {"on": "form.cancelled", "close": True},
        # ecobuild profile add <名前> --configuration <構成>
        {"on": "form.submitted", "run": "profile add",
         "args": {"module": {"arg": "module"}, "name": {"payload": "values.name"}, "configuration": {"payload": "values.configuration"}},
         "notify": "ビルド設定を保存しました。", "close": True},
    ],
}
