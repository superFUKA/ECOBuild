"""プリセットにする（入力の窓）：モジュールの役を、このPCのプリセットとして保存する。名前を決める。"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・プリセットにする役の名前

SCREEN = {
    "root": "form",
    "window": {"title": "プリセットにする", "width": 560, "height": 320},
    "nodes": [
        {"id": "form", "part": "cfg-form", "props": {
            "title": "プリセットにする", "ok": "保存",
            "intro": "この役を、このPCのプリセットとして保存します（「このPCのプリセット」に入り、ほかのモジュールに写せます）。保存していない変更は入りません。",
            "values": {"name": {"arg": "name"}},
            "fields": [{"name": "name", "label": "プリセットの名前", "required": True}],
        }},
    ],
    "bindings": [
        {"on": "form.cancelled", "close": True},
        # ecobuild agent preset add <名前> --from-module <役の名前>
        {"on": "form.submitted", "run": "agent preset add",
         "args": {"module": {"arg": "module"}, "name": {"payload": "values.name"}, "from_module": {"arg": "name"}},
         "notify": "プリセットにしました。", "close": True},
    ],
}
