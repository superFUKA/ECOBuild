"""ブランチ同士の提出：ブランチ → 取り込み先・提出の状態・URL と、取り込むボタン。届いている提出の一覧から、窓の中に重ねて開く。

取り込めるか（下書きでない・処理できる人か）は、部品が、読んだ答え（branch list・account show の take_in）のとおりに出す。
「取り込む」は、入力の窓（CI が失敗していても取り込むか）を重ねて開く。
"""

ARGS = {"module": ".", "branch": ""}  # モジュールのフォルダー・提出しているブランチの名前

SCREEN = {
    "root": "page",
    "window": {"title": "ブランチの提出", "width": 760, "height": 420},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "detail"]},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "close"]},
        {"id": "title", "part": "note", "props": {"text": "ブランチの提出", "heading": True}},
        {"id": "close", "part": "button", "props": {"label": "閉じる"}},
        {"id": "detail", "part": "review-submission", "props": {"name": {"arg": "branch"}}},
    ],
    "bindings": [
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "detail.branches"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "detail.access"},
        {"on": "close.pressed", "close": True},
        {"on": "detail.action", "when": {"action": "merge"}, "open": "review-form", "inside": True,
         "args": {"module": {"arg": "module"}, "kind": "merge", "id": {"payload": "id"}, "base": {"payload": "base"}}},
    ],
}
