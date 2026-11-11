"""ビルド設定を追加・編集（入力の窓）：名前・構成・並列の数（型が Python のモジュール）。設定の画面から、窓の中に重ねて開く。"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・編集するビルド設定の名前（追加なら空）

SCREEN = {
    "root": "form",
    "window": {"title": "ビルド設定", "width": 560, "height": 480},
    "nodes": [
        {"id": "form", "part": "cfg-form", "props": {
            "title": "ビルド設定", "ok": "保存",
            "intro": "同じ名前のビルド設定があれば置き換えます。ecobuild.toml が変わるので、タスクブランチでコミットしてください。",
            "at": [{"arg": "name"}],
            "fields": [
                {"name": "name", "label": "名前", "required": True, "value": {"arg": "name"}, "placeholder": "例：release"},
                {"name": "configuration", "label": "構成", "type": "select", "value": "Debug", "options": [
                    {"value": "Debug", "label": "Debug（開発用：.venv に編集可能で入れる）"},
                    {"value": "Release", "label": "Release（配布用：wheel・sdist も作る）"}]},
                {"name": "parallel", "label": "並列の数", "type": "number", "min": 1, "value": 1},
            ],
        }},
    ],
    "bindings": [
        {"read": "profile list", "args": {"module": {"arg": "module"}}, "to": "form.values", "from": "profiles"},
        {"on": "form.cancelled", "close": True},
        # ecobuild profile add <名前> --configuration <構成> --parallel <数>
        {"on": "form.submitted", "run": "profile add",
         "args": {"module": {"arg": "module"}, "name": {"payload": "values.name"}, "configuration": {"payload": "values.configuration"},
                  "parallel": {"payload": "values.parallel"}},
         "notify": "ビルド設定を保存しました。", "close": True},
    ],
}
