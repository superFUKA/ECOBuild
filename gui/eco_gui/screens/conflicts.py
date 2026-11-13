"""作業空間 › 衝突を直す：衝突したファイルの箇所ごとに、どちらの側を使うかを選ぶ。結果は手でも直せる。全部直したら続ける。

読むのは ecobuild sync conflicts（衝突したファイルと箇所）。選んだ側・直している途中の文字は部品の中にあり、保存で
ecobuild sync resolve <ファイル> --text（標準入力）に渡す。「続ける」は、全部のファイルを直して保存するまで押せない。
"""

ARGS = {"module": ".", "path": ""}  # 作業空間のフォルダー・初めに出すファイル（右クリックしたファイル。空なら先頭）

SCREEN = {
    "root": "page",
    "window": {"title": "衝突を直す", "width": 1280, "height": 860},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "conflict"]},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "衝突を直す", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "hint": "ファイルを読み直す（エディターで直した後に）"}},
        {"id": "conflict", "part": "review-conflict", "props": {"first": {"arg": "path"}}},
    ],
    "bindings": [
        # 読む（ecobuild sync conflicts・ecobuild status）
        {"read": "sync conflicts", "args": {"module": {"arg": "module"}}, "to": "conflict.data"},
        {"read": "status", "args": {"module": {"arg": "module"}}, "to": "conflict.status"},
        {"on": "reload.pressed", "refresh": True},
        # 保存：直した中身をファイルに書く（ecobuild sync resolve <ファイル> --text -。登録はしない）
        {"on": "conflict.saved", "run": "sync resolve",
         "args": {"module": {"arg": "module"}, "path": {"payload": "path"}, "text": {"payload": "text"}}, "notify": "保存しました。"},
        # ファイル全体を片方の側に（ecobuild sync take <ファイル> --side current|incoming。ファイルが空の並びなら、衝突したファイル全部）
        {"on": "conflict.taken", "run": "sync take",
         "args": {"module": {"arg": "module"}, "paths": {"payload": "paths"}, "side": {"payload": "side"}}},
        # TortoiseGit で直す（ecobuild diff <ファイル> --gui：衝突したファイルは TortoiseGitMerge の直す画面）
        {"on": "conflict.tortoise", "run": "diff", "args": {"module": {"arg": "module"}, "paths": [{"payload": "path"}], "gui": True}},
        # 続ける・やめる（ecobuild sync continue・ecobuild sync abort）。終わったら、この窓を閉じる
        {"on": "conflict.continued", "run": "sync continue", "args": {"module": {"arg": "module"}},
         "notify": "止まっていた操作を完了しました。", "close": True},
        {"on": "conflict.aborted", "run": "sync abort", "args": {"module": {"arg": "module"}},
         "notify": "やめて、前の状態に戻しました。", "close": True},
    ],
}
