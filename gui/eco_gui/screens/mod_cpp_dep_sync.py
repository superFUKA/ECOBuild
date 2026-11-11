"""モジュール › 依存先 › 手元を記録に合わせる：入力の窓。手元の依存先を、記録してある版にそろえる（ecobuild deps sync）。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "手元を記録に合わせる", "width": 600, "height": 320},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "手元を記録に合わせる", "ok": "合わせる",
            "intro": "手元の依存先を、記録してある版にそろえます。手元にないものは取ってきます。作業中のものや変更のあるものはそのままにします。",
            "fields": []}},
    ],
    "bindings": [
        {"on": "form.submitted", "run": "deps sync", "args": {"module": {"arg": "module"}}, "notify": "依存先を記録の版に合わせました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
