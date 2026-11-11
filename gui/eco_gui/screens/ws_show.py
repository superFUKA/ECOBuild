"""作業空間 › コミットの変更：1つのコミットの変更を、ファイルごとに畳んで見せる（窓の中に重ねて開く）。"""

ARGS = {"module": ".", "commit": ""}  # 作業空間のフォルダー・見るコミット

SCREEN = {
    "root": "page",
    "window": {"title": "コミットの変更", "width": 1040, "height": 760},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["detail", "foot"]},
        {"id": "detail", "part": "ws-diff", "props": {"title": "コミットの変更", "sha": {"arg": "commit"}}},
        {"id": "foot", "layout": "row", "look": "actions", "children": ["external", "close"]},
        {"id": "external", "part": "button", "props": {"label": "TortoiseGit で表示", "hint": "ecobuild show --gui（TortoiseGit が要ります）"}},
        {"id": "close", "part": "button", "props": {"label": "閉じる"}},
    ],
    "bindings": [
        {"read": "show", "args": {"module": {"arg": "module"}, "commit": {"arg": "commit"}}, "to": "detail.text"},
        # この PC の道具で見る（ecobuild show --gui：TortoiseGit を開く。なければ、ecobuild がそう答える）
        {"on": "external.pressed", "run": "show", "args": {"module": {"arg": "module"}, "commit": {"arg": "commit"}, "gui": True}},
        {"on": "close.pressed", "close": True},
    ],
}
