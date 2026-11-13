"""モジュール › ブランチ › 取り込み・提出：選んだブランチを、別のブランチへ提出する・直接取り込む。

上に、このブランチの提出（提出する…／作ってある提出を取り込む…：入力の窓を重ねて開く）。
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
        # このブランチの提出
        {"id": "own", "layout": "row", "look": "review-merge-own", "children": ["own_text", "submit", "merge_submission"]},
        {"id": "own_text", "part": "note", "props": {
            "text": "提出（PR）で、見てもらってから取り込みます。", "tone": "muted"}},
        {"id": "submit", "part": "button", "props": {"label": "提出する…", "hint": "取り込み先への提出を作る（ecobuild branch submit）"}},
        {"id": "merge_submission", "part": "button", "props": {
            "label": "このブランチの提出を取り込む…", "hint": "もう作ってある提出（branch submit）を、マージコミットで取り込む"}},
        # 提出なしで直接：ブランチ同士の取り込みのカード（選んでいるブランチは、初めは取り込むブランチの側。畳まない）
        {"id": "card", "screen": "review-branch-merge", "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "side": "from", "fold": False}},
    ],
    "bindings": [
        {"on": "reload.pressed", "refresh": True},
        {"on": "back.pressed", "open": "branches", "args": {"module": {"arg": "module"}}, "here": True},
        # 提出する（ecobuild branch submit <ブランチ> --into <先> [--title <題名>]）：入力の窓。取り込み先の初めの値は、カードで選んでいるもの
        {"on": "submit.pressed", "open": "review-branch-submit", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "into": {"value": "merge_into"}}},
        # 提出を取り込む（ecobuild branch merge <ブランチ> [--ignore-checks]）：入力の窓（CI が失敗していても取り込むか）を重ねて開く
        {"on": "merge_submission.pressed", "open": "review-merge", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}}},
    ],
}
