"""このPCのスキルにする（入力の窓）：モジュールのスキルを、このPCのスキルとして保存する。名前を決める。"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・このPCのスキルにするスキルの名前

SCREEN = {
    "root": "form",
    "window": {"title": "このPCのスキルにする", "width": 560, "height": 320},
    "nodes": [
        {"id": "form", "part": "cfg-form", "props": {
            "title": "このPCのスキルにする", "ok": "保存",
            "intro": "このスキルを、このPCのスキルとして保存します（「このPCのプリセット」に入り、ほかのモジュールに写せます）。保存していない変更は入りません。",
            "values": {"name": {"arg": "name"}},
            "fields": [{"name": "name", "label": "名前", "required": True}],
        }},
    ],
    "bindings": [
        {"on": "form.cancelled", "close": True},
        # ecobuild agent skill preset add <名前> --from-module <スキルの名前>
        {"on": "form.submitted", "run": "agent skill preset add",
         "args": {"module": {"arg": "module"}, "name": {"payload": "values.name"}, "from_module": {"arg": "name"}},
         "notify": "このPCのスキルにしました。", "close": True},
    ],
}
