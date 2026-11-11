"""作業空間 › 退避の一覧：このブランチで退避した変更の一覧。退避する・選んで戻す・選んで削除する。

変更の一覧の「退避 ▾」の「退避の一覧…」から開く。退避はモジュールの作業空間すべてで共有なので、ほかのブランチの退避は、数と一覧だけ
（それぞれの作業空間で扱う）。
"""

ARGS = {"module": "."}  # 作業空間のフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "退避の一覧", "width": 720, "height": 520, "refresh": {"focus": True}},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-page", "children": ["head", "place", "list"]},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "退避の一覧", "heading": True}},
        {"id": "place", "part": "note", "props": {"text": {"arg": "module"}, "tone": "muted"}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        {"id": "list", "part": "ws-stashes"},
    ],
    "bindings": [
        {"read": "stash list", "args": {"module": {"arg": "module"}}, "to": "list.stashes"},
        {"read": "status", "args": {"module": {"arg": "module"}}, "to": "list.status"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "list.reload", "refresh": True},
        # ecobuild stash・stash pop <番号>・stash drop <番号>（削除は、本体が確かめてから）
        {"on": "list.action", "when": {"name": "stash"}, "run": "stash", "args": {"module": {"arg": "module"}}, "notify": "変更を退避しました。"},
        {"on": "list.action", "when": {"name": "pop"}, "run": "stash pop", "args": {"module": {"arg": "module"}, "index": {"payload": "index"}},
         "notify": "退避した変更を戻しました。"},
        {"on": "list.action", "when": {"name": "drop"}, "run": "stash drop", "args": {"module": {"arg": "module"}, "index": {"payload": "index"}},
         "notify": "退避した変更を削除しました。"},
    ],
}
