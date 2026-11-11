"""モジュール › パイプライン：名前を付けた確認の並び（カード）と、操作のタイミングへの当て方（表）。作る・変える・消す・流す。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "パイプライン", "width": 1280, "height": 820, "refresh": {"focus": True}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "section", "body"]},
        {"id": "section", "screen": "mod-tabs", "args": {"current": "pipelines", "module": {"arg": "module"}}},
        {"id": "nav", "screen": "menu", "args": {"current": "overview", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "モジュール", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        {"id": "body", "layout": "column", "look": "mod-narrow", "children": ["place_note", "list", "timings", "skip_note"]},
        {"id": "place_note", "part": "note", "props": {"tone": "muted", "text":
            "パイプラインと当て方は、タスクブランチ（作業空間）で変えます（コミットして提出し、取り込まれると、モジュールで共有されます）。"
            "「このPCで足す」は、どこでも使えます。"}},
        {"id": "list", "part": "mod-pipeline-cards"},
        {"id": "timings", "part": "mod-timings"},
        {"id": "skip_note", "part": "note", "props": {"tone": "muted", "text":
            "走らせずに進めたいときは、コマンドに --no-pipelines（提出は --no-check）を付けます。GitHub の CI は「CI」のページです。"}},
    ],
    "bindings": [
        {"read": "pipeline list", "args": {"module": {"arg": "module"}}, "to": "list.data"},
        {"read": "pipeline list", "args": {"module": {"arg": "module"}}, "to": "timings.data"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "list.reload", "refresh": True},
        # カードのボタン：流す（ここで）。作る・変える・消すは、入力の窓（今の中身が初めの値）
        {"on": "list.action", "when": {"action": "run"}, "run": "pipeline run", "args": {"module": {"arg": "module"}, "name": {"payload": "name"}},
         "notify": "パイプラインが通りました。"},
        {"on": "list.action", "when": {"action": "add"}, "open": "mod-pipeline-edit", "inside": True, "args": {"module": {"arg": "module"}}},
        {"on": "list.action", "when": {"action": "edit"}, "open": "mod-pipeline-edit", "inside": True, "args": {
            "module": {"arg": "module"}, "name": {"payload": "name"}, "steps": {"payload": "steps"}, "tests": {"payload": "tests"}}},
        {"on": "list.action", "when": {"action": "remove"}, "open": "mod-pipeline-remove", "inside": True, "args": {
            "module": {"arg": "module"}, "name": {"payload": "name"}, "used": {"payload": "used"}}},
        # タイミングの行：モジュールの当て方を変える（タスクブランチで）・この PC だけで足す
        {"on": "timings.changed", "when": {"local": False}, "open": "mod-pipeline-timing", "inside": True, "args": {
            "module": {"arg": "module"}, "timing": {"payload": "timing"}, "names": {"payload": "names"}, "label": {"payload": "label"}}},
        {"on": "timings.changed", "when": {"local": True}, "open": "mod-pipeline-local", "inside": True, "args": {
            "module": {"arg": "module"}, "timing": {"payload": "timing"}, "names": {"payload": "names"}, "label": {"payload": "label"}}},
    ],
}
