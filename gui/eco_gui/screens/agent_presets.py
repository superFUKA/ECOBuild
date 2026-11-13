"""モジュール › エージェント › このPCのプリセット：モジュールの窓の中で、このPCのエージェントの設定（画面 pc-agents）を見せる。"""

ARGS = {"module": "."}  # モジュールのフォルダー（エージェントの画面へ戻るため。プリセットはこのPCのもので、モジュールによらない）

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "このPCのプリセット", "width": 1280, "height": 820},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["back_row", "section", "body"]},
        {"id": "section", "screen": "mod-tabs", "args": {"current": "agents", "module": {"arg": "module"}}},
        {"id": "nav", "screen": "menu", "args": {"current": "overview", "module": {"arg": "module"}}},
        {"id": "back_row", "layout": "row", "look": "tools", "children": ["back"]},
        {"id": "back", "part": "button", "props": {"label": "← モジュールのエージェントへ戻る", "quiet": True}},
        {"id": "body", "screen": "pc-agents"},
    ],
    "bindings": [
        {"on": "back.pressed", "open": "agents", "args": {"module": {"arg": "module"}}, "here": True},
    ],
}
