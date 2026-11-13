"""作業空間 › 新しいファイル：まだ git の管理に入っていないファイルの中身を見せる（窓の中に重ねて開く）。

新しいファイルには比べる前がないので、TortoiseGit の差分には送らない（前の GUI と同じ）。中身は ecobuild diff <ファイル>
（名指しした新しいファイルは、中身を足した行として出る）。"""

ARGS = {"module": ".", "paths": []}  # 作業空間のフォルダー・見るファイル

SCREEN = {
    "root": "page",
    "window": {"title": "新しいファイル", "width": 1040, "height": 760},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["title", "target", "content", "foot"]},
        {"id": "title", "part": "note", "props": {"text": "新しいファイル", "heading": True}},
        {"id": "target", "part": "string-list", "props": {"items": {"arg": "paths"}}},
        {"id": "content", "part": "ws-diff", "props": {"title": "中身（まだ git の管理に入っていません）", "empty_text": "中身は空です。"}},
        {"id": "foot", "layout": "row", "look": "actions", "children": ["close"]},
        {"id": "close", "part": "button", "props": {"label": "閉じる"}},
    ],
    "bindings": [
        {"read": "diff", "args": {"module": {"arg": "module"}, "paths": {"arg": "paths"}}, "to": "content.text"},
        {"on": "close.pressed", "close": True},
    ],
}
