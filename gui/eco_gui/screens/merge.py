"""モジュール › ブランチ › 取り込み・提出：選んだブランチを、別のブランチへ提出する・直接取り込む。

上に、このブランチの提出（提出が出ていれば「取り込む…」、出ていなくて既定のブランチでなければ「提出する…」：入力の窓を重ねて開く）。
下に、ブランチ同士の取り込みのカード（画面 review-branch-merge：向きの入れ替え・相手の選択・取り込む前の確かめ）。
"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・取り込む（提出する）ブランチ

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "ブランチの取り込み・提出", "width": 1280, "height": 820},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "own", "card"]},
        {"id": "nav", "screen": "menu", "args": {"current": "branches", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "tools"]},
        {"id": "title", "part": "note", "props": {"text": {"arg": "name"}, "prefix": "ブランチの取り込み・提出：", "heading": True}},
        {"id": "tools", "layout": "row", "look": "tools", "children": ["back", "reload"]},
        {"id": "back", "part": "button", "props": {"label": "← ブランチ", "quiet": True, "hint": "ブランチの一覧へ戻る"}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        # このブランチの提出：出ていれば「取り込む…」、出ていなければ「提出する…」（既定のブランチは提出しない）
        {"id": "own", "part": "mod-branch-own", "props": {"name": {"arg": "name"}}},
        # 提出なしで直接：ブランチ同士の取り込みのカード（選んでいるブランチは、初めは取り込むブランチの側。畳まない）
        {"id": "card", "screen": "review-branch-merge", "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "side": "from", "fold": False}},
    ],
    "bindings": [
        {"on": "reload.pressed", "refresh": True},
        {"on": "back.pressed", "open": "branches", "args": {"module": {"arg": "module"}}, "here": True},
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "own.branches"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "own.access"},
        # 提出する（ecobuild branch submit <ブランチ> --into <先> [--title <題名>]）：入力の窓。取り込み先の初めの値は、カードで選んでいるもの
        {"on": "own.action", "when": {"action": "submit"}, "open": "review-branch-submit", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "into": {"value": "merge_into"}}},
        # 提出を取り込む（ecobuild branch merge <ブランチ> [--ignore-checks]）：入力の窓（CI が失敗していても取り込むか）を重ねて開く
        {"on": "own.action", "when": {"action": "merge"}, "open": "review-merge", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}}},
    ],
}
