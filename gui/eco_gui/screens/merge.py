"""モジュール › ブランチ › 取り込み・提出：選んだブランチを、別のブランチへ直接取り込む・提出する。

取り込み先を下の表から選ぶと、上のボタンが押せるようになる（選ぶまでは灰色）。
"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・取り込む（提出する）ブランチ

SCREEN = {
    "root": "page",
    "window": {"title": "ブランチの取り込み・提出", "width": 1280, "height": 820},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "source", "own", "chosen", "direct", "submit_form",
                                                        "targets_title", "targets"]},
        {"id": "nav", "screen": "menu", "args": {"current": "branches", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "ブランチの取り込み・提出", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "source", "part": "note", "props": {"prefix": "取り込む（提出する）ブランチ：", "text": {"arg": "name"}}},
        {"id": "own", "layout": "row", "children": ["merge_submission"]},
        {"id": "merge_submission", "part": "button", "props": {
            "label": "このブランチの提出を取り込む…", "hint": "もう作ってある提出（branch submit）を、マージコミットで取り込む"}},
        {"id": "targets_title", "part": "note", "props": {"text": "取り込み先を選ぶ"}},
        {"id": "targets", "part": "table", "props": {
            "columns": [{"key": "name", "label": "名前"}, {"key": "base", "label": "作成元"}, {"key": "remote", "label": "GitHub"},
                        {"key": "submitted_to", "label": "提出先"}],
            "key": "name",
            "labels": {"remote": {"true": "ある", "false": ""}},
            "actions": [{"name": "choose", "label": "ここへ"}],
            "empty_text": "ブランチはありません。",
        }},
        {"id": "chosen", "part": "note", "props": {"prefix": "取り込み先（下の表から選ぶ）："}},
        # 選んだ取り込み先へ（選ぶまで押せない）
        {"id": "direct", "layout": "row", "children": ["merge", "resolve"]},
        {"id": "merge", "part": "button", "props": {
            "label": "直接取り込む", "primary": True, "hint": "提出を作らずに取り込む（入るコミット・変わるファイル・衝突を、確認で見せます）"}},
        {"id": "resolve", "part": "button", "props": {"label": "衝突を直すタスクを作る", "hint": "直接取り込めないとき、衝突を直すためのタスクとタスクブランチを作る"}},
        {"id": "submit_form", "layout": "row", "children": ["submit_title", "submit"]},
        {"id": "submit_title", "part": "text-input", "props": {"title": "提出の題名（空なら既定）", "placeholder": "任意"}},
        {"id": "submit", "part": "button", "props": {"label": "提出する", "hint": "取り込み先への提出を作る（見てもらってから取り込む）"}},
    ],
    "bindings": [
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "targets.rows"},
        {"on": "reload.pressed", "refresh": True},
        # 取り込み先を選ぶ
        {"on": "targets.action", "when": {"action": "choose"}, "set": {"merge_into": {"payload": "id"}}},
        {"value": "merge_into", "to": "chosen.text"},
        {"on": "submit_title.changed", "set": {"submit_title": {"payload": "text"}}},
        {"value": "submit_title", "to": "submit_title.text"},
        # 提出を取り込む（ecobuild branch merge <ブランチ> [--ignore-checks]）：入力の窓（CI が失敗していても取り込むか）を重ねて開く
        {"on": "merge_submission.pressed", "open": "review-form", "inside": True,
         "args": {"module": {"arg": "module"}, "kind": "merge", "id": {"arg": "name"}}},
        # 選んだ取り込み先へ（ecobuild branch merge <ブランチ> --into <先>・branch resolve <ブランチ> --into <先>・
        # branch submit <ブランチ> --into <先> [--title <題名>]）。取り込み先は、コマンドでは任意でも、選ぶまで実行しない
        # （省くと、branch merge は「提出を取り込む」になるため）
        {"on": "merge.pressed", "run": "branch merge", "require": ["into"],
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "into": {"value": "merge_into"}}, "set": {"merge_into": None}},
        {"on": "resolve.pressed", "run": "branch resolve", "require": ["into"],
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "into": {"value": "merge_into"}}},
        {"on": "submit.pressed", "run": "branch submit", "require": ["into"],
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "into": {"value": "merge_into"}, "title": {"value": "submit_title"}},
         "set": {"submit_title": None}},
    ],
}
