"""作業空間 › 差分：まだコミットしていない変更を、比べ方ごとのタブで見せる（窓の中に重ねて開く）。

ステージしていない変更／ステージ済みの変更／作成元との差分（提出で出る差分）。paths が空なら、全部のファイル。"""

ARGS = {"module": ".", "paths": []}  # 作業空間のフォルダー・見るファイル（空なら全部）

SCREEN = {
    "root": "page",
    "window": {"title": "差分", "width": 1040, "height": 760},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["title", "target", "modes", "foot"]},
        {"id": "title", "part": "note", "props": {"text": "差分", "heading": True}},
        {"id": "target", "part": "string-list", "props": {"items": {"arg": "paths"}, "empty_text": "すべてのファイル"}},
        {"id": "modes", "layout": "tabs", "props": {"labels": ["ステージしていない変更", "ステージ済みの変更", "作成元との差分（提出で出る差分）"]},
         "children": ["unstaged", "staged", "base"]},
        {"id": "unstaged", "part": "ws-diff", "props": {
            "title": "ステージしていない変更", "empty_text": "ステージしていない変更はありません（新しいファイルには、まだ差分がありません）。"}},
        {"id": "staged", "part": "ws-diff", "props": {"title": "ステージ済みの変更", "empty_text": "ステージ済みの変更はありません。"}},
        {"id": "base", "part": "ws-diff", "props": {"title": "作成元との差分", "empty_text": "作成元との差分はありません。"}},
        {"id": "foot", "layout": "row", "look": "actions", "children": ["external", "close"]},
        {"id": "external", "part": "button", "props": {"label": "TortoiseGit で表示", "hint": "ecobuild diff --gui（TortoiseGit が要ります）"}},
        {"id": "close", "part": "button", "props": {"label": "閉じる"}},
    ],
    "bindings": [
        {"read": "diff", "args": {"module": {"arg": "module"}, "paths": {"arg": "paths"}}, "to": "unstaged.text"},
        {"read": "diff", "args": {"module": {"arg": "module"}, "paths": {"arg": "paths"}, "staged": True}, "to": "staged.text"},
        {"read": "diff", "args": {"module": {"arg": "module"}, "paths": {"arg": "paths"}, "base": True}, "to": "base.text"},
        # この PC の道具で見る（ecobuild diff --gui：TortoiseGit を開く。なければ、ecobuild がそう答える）
        {"on": "external.pressed", "run": "diff", "args": {"module": {"arg": "module"}, "paths": {"arg": "paths"}, "gui": True}},
        {"on": "close.pressed", "close": True},
    ],
}
