"""作業空間 › 衝突を直す：衝突したファイルを、片方の側で解決する。直し終えたら続ける。やめて前に戻すこともできる。

解決のボタンは、止まっている操作があるとき（status の stopped）だけ出す。1つのファイルを採るボタンは、ファイルを選ぶまで押せない。
"""

ARGS = {"module": "."}  # 作業空間のフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "衝突を直す", "width": 900, "height": 720},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "state", "guide", "body", "selected", "one", "all", "finish"]},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "衝突を直す", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "state", "part": "facts", "props": {
            "items": [{"key": "branch", "label": "ブランチ"}, {"key": "stopped", "label": "止まっている操作"},
                      {"key": "conflicted", "label": "衝突したファイル"}],
            "labels": {"stopped": {"merge": "取り込み", "rebase": "タスクブランチの作り直し", "revert": "取り消し",
                                   "stash": "退避した変更の戻し", "": "ありません"}},
        }},
        {"id": "guide", "part": "note", "props": {
            "text": "ファイルを選ぶと、衝突の中身が出ます。片方の側を採るか、エディターで直して保存してから「続ける」を押します。"}},
        {"id": "body", "layout": "row", "children": ["files", "diff"]},
        {"id": "files", "part": "tree", "props": {"empty_text": "衝突したファイルはありません。"}},
        {"id": "diff", "part": "text-view", "props": {"empty_text": "ファイルを選ぶと、衝突の中身が出ます。"}},
        {"id": "selected", "part": "note", "props": {"prefix": "選んでいるファイル："}},
        {"id": "one", "layout": "row", "children": ["take_current", "take_incoming"]},
        {"id": "take_current", "part": "button", "props": {"label": "今の側を採る", "hint": "選んだファイルを、今いるブランチの側の中身にする"}},
        {"id": "take_incoming", "part": "button", "props": {"label": "入ってくる側を採る", "hint": "選んだファイルを、取り込む側の中身にする"}},
        {"id": "all", "layout": "row", "children": ["all_current", "all_incoming"]},
        {"id": "all_current", "part": "button", "props": {"label": "全部を今の側に"}},
        {"id": "all_incoming", "part": "button", "props": {"label": "全部を入ってくる側に"}},
        {"id": "finish", "layout": "row", "children": ["abort", "continue"]},
        {"id": "abort", "part": "button", "props": {"label": "やめて前に戻す", "hint": "止まっている操作をやめる"}},
        {"id": "continue", "part": "button", "props": {"label": "続ける", "primary": True, "hint": "直したファイルを登録して、止まっている操作を完了する"}},
    ],
    "bindings": [
        # 読む：status は1回だけ実行され、2つの部品へ出る
        {"read": "status", "args": {"module": {"arg": "module"}}, "to": "state.data"},
        {"read": "status", "args": {"module": {"arg": "module"}}, "to": "files.paths", "from": "conflicted"},
        {"on": "reload.pressed", "refresh": True},
        # 選んだファイル。chosen は、コマンドの「ファイルの並び」の引数へそのまま渡す形（選んだ1つだけの並び）
        {"on": "files.selected", "set": {"file": {"payload": "path"}, "chosen": [{"payload": "path"}]}},
        {"value": "file", "to": "files.selected"},
        {"value": "file", "to": "selected.text"},
        {"read": "diff", "args": {"module": {"arg": "module"}, "paths": [{"value": "file"}]}, "to": "diff.text"},
        # 止まっている操作があるときだけ、解決のボタンを出す
        {"read": "status", "args": {"module": {"arg": "module"}}, "into": "stopped", "from": "stopped"},
        {"show": "take_current", "when": {"stopped": ["merge", "rebase", "revert", "stash"]}},
        {"show": "take_incoming", "when": {"stopped": ["merge", "rebase", "revert", "stash"]}},
        {"show": "all_current", "when": {"stopped": ["merge", "rebase", "revert", "stash"]}},
        {"show": "all_incoming", "when": {"stopped": ["merge", "rebase", "revert", "stash"]}},
        {"show": "abort", "when": {"stopped": ["merge", "rebase", "revert", "stash"]}},
        {"show": "continue", "when": {"stopped": ["merge", "rebase", "revert", "stash"]}},
        # 片方の側を採る（ecobuild sync take <ファイル> --side current|incoming）。ファイルは、コマンドでは任意（省くと全部）でも、
        # 選ぶまで実行しない
        {"on": "take_current.pressed", "run": "sync take", "require": ["paths"],
         "args": {"module": {"arg": "module"}, "paths": {"value": "chosen"}, "side": "current"}, "set": {"file": None, "chosen": None}},
        {"on": "take_incoming.pressed", "run": "sync take", "require": ["paths"],
         "args": {"module": {"arg": "module"}, "paths": {"value": "chosen"}, "side": "incoming"}, "set": {"file": None, "chosen": None}},
        # 全部を片方の側に（ecobuild sync take --side current|incoming。ファイルを省くと、衝突したファイル全部）
        {"on": "all_current.pressed", "run": "sync take", "args": {"module": {"arg": "module"}, "side": "current"},
         "set": {"file": None, "chosen": None}},
        {"on": "all_incoming.pressed", "run": "sync take", "args": {"module": {"arg": "module"}, "side": "incoming"},
         "set": {"file": None, "chosen": None}},
        # 続ける・やめる（ecobuild sync continue・ecobuild sync abort）
        {"on": "continue.pressed", "run": "sync continue", "args": {"module": {"arg": "module"}}, "set": {"file": None, "chosen": None}},
        {"on": "abort.pressed", "run": "sync abort", "args": {"module": {"arg": "module"}}, "set": {"file": None, "chosen": None}},
    ],
}
