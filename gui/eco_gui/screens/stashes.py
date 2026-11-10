"""作業空間 › 退避：退避した変更の一覧。退避する・戻す・捨てる。"""

ARGS = {"module": "."}  # 作業空間のフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "退避した変更", "width": 640, "height": 480},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "list", "actions", "about"]},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": {"arg": "module"}, "prefix": "退避した変更：", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "list", "part": "string-list", "props": {
            "numbered": True, "first_mark": "← 戻す・捨てるのは、これ（最後に退避したもの）", "empty_text": "退避した変更はありません。"}},
        {"id": "actions", "layout": "row", "children": ["stash", "pop", "drop"]},
        {"id": "stash", "part": "button", "props": {"label": "今の変更を退避", "hint": "まだコミットしていない変更を、いったんよける"}},
        {"id": "pop", "part": "button", "props": {"label": "最後の退避を戻す", "primary": True}},
        {"id": "drop", "part": "button", "props": {"label": "最後の退避を捨てる"}},
        {"id": "about", "part": "note", "props": {"text": "ecobuild stash pop・stash drop は、最後に退避したものを相手にします。"}},
    ],
    "bindings": [
        {"read": "stash list", "args": {"module": {"arg": "module"}}, "to": "list.items"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "stash.pressed", "run": "stash", "args": {"module": {"arg": "module"}}},
        {"on": "pop.pressed", "run": "stash pop", "args": {"module": {"arg": "module"}}},
        {"on": "drop.pressed", "run": "stash drop", "args": {"module": {"arg": "module"}}},
    ],
}
