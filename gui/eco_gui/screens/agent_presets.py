"""モジュール › エージェント › このPCのプリセット：モジュールの窓の中で、このPCのエージェントの設定（画面 pc-agents）を見せる。"""

ARGS = {"module": "."}  # モジュールのフォルダー（メニューで戻るため。プリセットはこのPCのもので、モジュールによらない）

SCREEN = {
    "root": "page",
    "window": {"title": "このPCのプリセット", "width": 980, "height": 820},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "sub", "body"]},
        {"id": "nav", "screen": "menu", "args": {"current": "agents", "module": {"arg": "module"}}},
        {"id": "sub", "screen": "agents-menu", "args": {"current": "agent-presets", "module": {"arg": "module"}}},
        {"id": "body", "screen": "pc-agents"},
    ],
    "bindings": [],
}
