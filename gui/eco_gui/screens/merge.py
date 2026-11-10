"""モジュール › ブランチ › 取り込み・提出：選んだブランチを、別のブランチへ直接取り込む・提出する。"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・取り込む（提出する）ブランチ

SCREEN = {
    "root": "page",
    "window": {"title": "ブランチの取り込み・提出", "width": 900, "height": 680},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "head", "source", "own", "targets_title", "submit_title", "targets"]},
        {"id": "nav", "screen": "menu", "args": {"current": "branches", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "ブランチの取り込み・提出", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "source", "part": "note", "props": {"prefix": "取り込む（提出する）ブランチ：", "text": {"arg": "name"}}},
        {"id": "own", "layout": "row", "children": ["merge_submission"]},
        {"id": "merge_submission", "part": "button", "props": {
            "label": "このブランチの提出を取り込む", "hint": "もう作ってある提出（branch submit）を、マージコミットで取り込む"}},
        {"id": "targets_title", "part": "note", "props": {"text": "取り込み先を選ぶ（直接取り込む前に、入るコミット・変わるファイル・衝突を確かめます）"}},
        {"id": "submit_title", "part": "text-input", "props": {"title": "提出の題名（「ここへ提出」のとき。空なら既定）", "placeholder": "任意"}},
        {"id": "targets", "part": "table", "props": {
            "columns": [{"key": "name", "label": "名前"}, {"key": "base", "label": "作成元"}, {"key": "remote", "label": "GitHub"},
                        {"key": "submitted_to", "label": "提出先"}],
            "key": "name",
            "labels": {"remote": {"true": "ある", "false": ""}},
            "actions": [{"name": "merge", "label": "ここへ取り込む"}, {"name": "submit", "label": "ここへ提出"},
                        {"name": "resolve", "label": "衝突を直すタスク"}],
            "empty_text": "ブランチはありません。",
        }},
    ],
    "bindings": [
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "targets.rows"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "submit_title.changed", "set": {"title": {"payload": "text"}}},
        # 提出を取り込む（ecobuild branch merge <ブランチ>）
        {"on": "merge_submission.pressed", "run": "branch merge", "args": {"module": {"arg": "module"}, "name": {"arg": "name"}}},
        # 行のボタン（ecobuild branch merge <ブランチ> --into <先>・branch submit <ブランチ> --into <先> [--title <題名>]・
        # branch resolve <ブランチ> --into <先>）
        {"on": "targets.action", "when": {"action": "merge"}, "run": "branch merge",
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "into": {"payload": "id"}}},
        {"on": "targets.action", "when": {"action": "submit"}, "run": "branch submit",
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "into": {"payload": "id"}, "title": {"value": "title"}}},
        {"on": "targets.action", "when": {"action": "resolve"}, "run": "branch resolve",
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "into": {"payload": "id"}}},
    ],
}
