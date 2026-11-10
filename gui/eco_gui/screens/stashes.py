"""作業空間 › 退避：退避した変更の一覧。退避する・選んで戻す・選んで捨てる。"""

ARGS = {"module": "."}  # 作業空間のフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "退避した変更", "width": 640, "height": 480},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "list", "actions", "about"]},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": {"arg": "module"}, "prefix": "退避した変更：", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "list", "part": "pick-list", "props": {"numbered": True, "empty_text": "退避した変更はありません。"}},
        {"id": "actions", "layout": "row", "children": ["stash", "pop", "drop"]},
        {"id": "stash", "part": "button", "props": {"label": "今の変更を退避", "hint": "まだコミットしていない変更を、いったんよける"}},
        {"id": "pop", "part": "button", "props": {"label": "戻す", "primary": True, "hint": "選んだ退避を戻す（選ばなければ、このブランチで最後に退避したもの）"}},
        {"id": "drop", "part": "button", "props": {"label": "捨てる", "hint": "選んだ退避を捨てる（選ばなければ、このブランチで最後に退避したもの）"}},
        {"id": "about", "part": "note", "props": {"text": "行を選ぶと、その退避を戻す・捨てる（ecobuild stash pop <番号>・stash drop <番号>）。選ばなければ、このブランチで最後に退避したもの。ほかのタスクブランチで退避したものは、ここでは戻せません。"}},
    ],
    "bindings": [
        {"read": "stash list", "args": {"module": {"arg": "module"}}, "to": "list.items"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "stash.pressed", "run": "stash", "args": {"module": {"arg": "module"}}},
        {"on": "list.selected", "set": {"stash": {"payload": "index"}}},
        {"value": "stash", "to": "list.selected"},
        # 戻す・捨てると番号がずれるので、選択は外す
        {"on": "pop.pressed", "run": "stash pop", "args": {"module": {"arg": "module"}, "index": {"value": "stash"}}, "set": {"stash": None}},
        {"on": "drop.pressed", "run": "stash drop", "args": {"module": {"arg": "module"}, "index": {"value": "stash"}}, "set": {"stash": None}},
    ],
}
