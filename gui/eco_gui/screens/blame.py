"""作業空間 › 注釈履歴：ファイルの各行を、最後に変えたコミット（SHA・だれが・いつ）と並べて見せる（ecobuild blame <ファイル>）。

エクスプローラー・変更の一覧の右クリックの「注釈履歴」から開く。コミットを押すと、その行を強調し、もう一度押す（か「変更を見る」）と、
そのコミットの変更を窓の中に重ねて開く。「ログ」は、このファイルを変えたコミットの一覧（ログの窓）。
"""

ARGS = {"module": ".", "path": ""}  # 作業空間のフォルダー・見るファイル

SCREEN = {
    "root": "page",
    "window": {"title": "注釈履歴", "width": 1100, "height": 780},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-fill-page", "children": ["head", "lines"]},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "tools"]},
        {"id": "title", "part": "note", "props": {"text": {"arg": "path"}, "prefix": "注釈履歴：", "heading": True}},
        {"id": "tools", "layout": "row", "look": "tools", "children": ["log", "external", "reload"]},
        {"id": "log", "part": "button", "props": {"label": "ログ", "quiet": True, "hint": "このファイルを変えたコミットの一覧を、ログの窓で開く"}},
        {"id": "external", "part": "button", "props": {"label": "TortoiseGit で表示", "quiet": True, "hint": "ecobuild blame --gui（TortoiseGit が要ります）"}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        {"id": "lines", "part": "ws-blame", "look": "ws-fill"},
    ],
    "bindings": [
        {"read": "blame", "args": {"module": {"arg": "module"}, "path": {"arg": "path"}}, "require": ["path"], "to": "lines.text"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "lines.selected", "set": {"blame_commit": {"payload": "commit"}}},
        {"value": "blame_commit", "to": "lines.selected"},
        {"on": "lines.opened", "run": "show", "args": {"module": {"arg": "module"}, "commit": {"payload": "commit"}, "gui": True},
         "instead": {"when": {"code": ["tool_missing", "revision_not_found"]}, "open": "ws-show", "args": {"module": {"arg": "module"}, "commit": {"payload": "commit"}}, "inside": True}},
        {"on": "log.pressed", "open": "ws-log", "args": {"module": {"arg": "module"}, "paths": [{"arg": "path"}]}},
        {"on": "external.pressed", "run": "blame", "args": {"module": {"arg": "module"}, "path": {"arg": "path"}, "gui": True}},
    ],
}
