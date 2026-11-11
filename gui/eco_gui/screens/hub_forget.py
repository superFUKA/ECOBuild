"""ハブ › 一覧から外す：モジュールを、この PC の一覧から外す前の確かめ（フォルダも GitHub のリポジトリも残る）。開けない理由があれば、それも出す。"""

ARGS = {"path": "", "name": "", "reason": ""}

SCREEN = {
    "root": "page",
    "window": {"title": "一覧から外す", "width": 540, "height": 340},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["title", "reason", "note", "path", "actions"]},
        {"id": "title", "part": "note", "props": {"text": {"arg": "name"}, "prefix": "一覧から外す：", "heading": True}},
        {"id": "reason", "part": "note", "props": {"text": {"arg": "reason"}, "tone": "warn"}},
        {"id": "note", "part": "note", "props": {"text": "この PC の一覧から外します。フォルダと GitHub のリポジトリには触りません（フォルダが残っていて不要なら、自分で削除してください）。なお、このフォルダで ecobuild を使うと（開発環境を開くなど）、再び一覧に表示されます。"}},
        {"id": "path", "part": "note", "props": {"text": {"arg": "path"}, "prefix": "フォルダ：", "tone": "muted"}},
        {"id": "actions", "layout": "row", "look": "actions", "children": ["cancel", "forget"]},
        {"id": "cancel", "part": "button", "props": {"label": "キャンセル"}},
        {"id": "forget", "part": "button", "props": {"label": "一覧から外す", "primary": True}},
    ],
    "bindings": [
        {"on": "cancel.pressed", "close": True},
        {"on": "forget.pressed", "run": "workspace forget", "args": {"path": {"arg": "path"}}, "notify": "一覧から外しました。", "close": True},
    ],
}
