"""ブランチ同士の取り込みのカード：共有ブランチを、提出（PR）なしで、別の共有ブランチへ直接取り込む。ほかの画面の中に置く
（{"id": …, "screen": "review-branch-merge", "args": {"module": …, "name": 選んでいるブランチ}}）。

選んでいるブランチを片側に固定し（初めは取り込み先。→ で入れ替える）、相手をセレクトで選ぶ。選ぶと、取り込む前の確かめ
（下見：ecobuild branch merge <名前> --into <先> --dry-run）がカードに出る：方式（早送り・マージコミット・衝突する・取り込み済み）、
入るコミット、変わるファイル、衝突するファイル、取り込める人。
「取り込む」は取り込めるとき、「衝突を直す…」は衝突するときだけ出る（方式は ecobuild の答え）。
"""

ARGS = {"module": ".", "name": "", "side": "into", "fold": True}  # モジュールのフォルダー・選んでいるブランチ・それを初めに置く側・畳めるカードか

SCREEN = {
    "root": "card",
    "window": {"title": "ブランチ同士の取り込み", "width": 860, "height": 620},
    "nodes": [
        {"id": "card", "layout": "column", "look": "review-merge-card", "children": ["pick", "plan", "go"]},
        {"id": "pick", "part": "review-merge-pick", "props": {"name": {"arg": "name"}, "side": {"arg": "side"}, "foldable": {"arg": "fold"}}},
        # 取り込む前の確かめ（下見の結果）
        {"id": "plan", "part": "review-merge-plan"},
        {"id": "go", "layout": "row", "look": "review-merge-go", "children": ["merge", "resolve"]},
        {"id": "merge", "part": "button", "props": {
            "label": "取り込む", "primary": True, "hint": "提出（PR）を作らずに、取り込み先へ直接取り込む（GitHub の取り込み先が変わります）"}},
        {"id": "resolve", "part": "button", "props": {
            "label": "衝突を直す…", "primary": True, "hint": "衝突を直すためのタスクとタスクブランチを作る（ecobuild branch resolve）"}},
    ],
    "bindings": [
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "pick.branches"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "pick.default_base", "from": "default_base"},
        # 組（取り込むブランチ・取り込み先）と、カードの開閉
        {"on": "pick.changed", "set": {"merge_source": {"payload": "source"}, "merge_into": {"payload": "into"}}},
        {"value": "merge_source", "to": "pick.source"},
        {"value": "merge_into", "to": "pick.into"},
        {"on": "pick.toggled", "set": {"merge_open": {"payload": "open"}}},
        {"value": "merge_open", "to": "pick.open"},
        {"on": "pick.reload", "refresh": True},
        {"show": "plan", "when": {"merge_open": True}},
        {"show": "go", "when": {"merge_open": True}},
        # 下見（何も変えない）：何が起きるかをカードへ。方式は、見出しの要約と、出すボタンを分けるのにも使う
        {"read": "branch merge", "preview": True, "require": ["name", "into"],
         "args": {"module": {"arg": "module"}, "name": {"value": "merge_source"}, "into": {"value": "merge_into"}}, "to": "plan.plan"},
        {"read": "branch merge", "preview": True, "require": ["name", "into"],
         "args": {"module": {"arg": "module"}, "name": {"value": "merge_source"}, "into": {"value": "merge_into"}}, "to": "pick.plan"},
        {"read": "branch merge", "preview": True, "require": ["name", "into"],
         "args": {"module": {"arg": "module"}, "name": {"value": "merge_source"}, "into": {"value": "merge_into"}}, "into": "merge_method", "from": "method"},
        {"show": "merge", "when": {"merge_method": ["fast-forward", "merge"]}},
        {"show": "resolve", "when": {"merge_method": "conflict"}},
        # 取り込む（ecobuild branch merge <ブランチ> --into <先>。確認は本体が出す）。取り込み先は、コマンドでは任意でも、選ぶまで実行しない
        # （省くと、branch merge は「提出を取り込む」になるため）。取り込んだ後は、読み直した下見が「取り込み済み」になる
        {"on": "merge.pressed", "run": "branch merge", "require": ["name", "into"],
         "args": {"module": {"arg": "module"}, "name": {"value": "merge_source"}, "into": {"value": "merge_into"}}, "notify": "ブランチを取り込みました。"},
        # 衝突を直す：何をするかを書いた入力の窓を重ねて開く（ecobuild branch resolve <ブランチ> --into <先>）
        {"on": "resolve.pressed", "open": "review-branch-resolve", "inside": True,
         "args": {"module": {"arg": "module"}, "name": {"value": "merge_source"}, "into": {"value": "merge_into"}}},
    ],
}
