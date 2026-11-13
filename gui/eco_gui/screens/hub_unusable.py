"""ハブ › 使えないモジュール：開けない理由（git の clone ではなくなった等）と、フォルダを開く・一覧から外す（窓の中に重ねて開く）。

フォルダと GitHub のリポジトリには触らない。不要なら「フォルダを開く」から自分で削除する。"""

ARGS = {"path": "", "name": "", "reason": ""}

SCREEN = {
    "root": "page",
    "window": {"title": "使えないモジュール", "width": 540, "height": 360},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["title", "reason", "note", "path", "actions"]},
        {"id": "title", "part": "note", "props": {"text": {"arg": "name"}, "prefix": "使えません：", "heading": True}},
        {"id": "reason", "part": "note", "props": {"text": {"arg": "reason"}, "tone": "warn"}},
        {"id": "note", "part": "note", "props": {"text": "この PC の一覧から外します。フォルダと GitHub のリポジトリはそのまま残ります。不要なら「フォルダを開く」から削除してください。"}},
        {"id": "path", "part": "note", "props": {"text": {"arg": "path"}, "prefix": "フォルダ：", "tone": "muted"}},
        {"id": "actions", "layout": "row", "look": "actions", "children": ["cancel", "folder", "forget"]},
        {"id": "cancel", "part": "button", "props": {"label": "キャンセル"}},
        {"id": "folder", "part": "button", "props": {"label": "フォルダを開く"}},
        {"id": "forget", "part": "button", "props": {"label": "一覧から外す", "primary": True}},
    ],
    "bindings": [
        {"on": "cancel.pressed", "close": True},
        {"on": "folder.pressed", "run": "open", "args": {"module": {"arg": "path"}, "app": "explorer"}},
        {"on": "forget.pressed", "run": "workspace forget", "args": {"path": {"arg": "path"}}, "notify": "一覧から外しました。", "close": True},
    ],
}
