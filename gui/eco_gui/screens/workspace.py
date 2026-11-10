"""作業空間：今のブランチと変更。コミット・Push・取り込み・提出。"""

ARGS = {"module": "."}  # 作業空間のフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "作業空間", "width": 820, "height": 760},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "state", "changes", "diff", "commit", "chosen", "actions", "tools", "more", "out", "log_title", "log"]},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": {"arg": "module"}, "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "state", "part": "facts", "props": {"items": [
            {"key": "branch", "label": "ブランチ"}, {"key": "task", "label": "タスク"}, {"key": "base", "label": "作成元"},
            {"key": "ahead", "label": "まだ送っていないコミット"}, {"key": "behind", "label": "まだ取り込んでいないコミット"},
        ]}},
        {"id": "changes", "part": "changes", "props": {"none_when_empty": True}},
        {"id": "diff", "part": "text-view", "props": {"empty_text": "ファイルの名前を押すと、差分が出ます。"}},
        {"id": "commit", "layout": "row", "children": ["message", "amend", "do_commit"]},
        {"id": "amend", "part": "toggle", "props": {"label": "直前のコミットを直す", "hint": "新しいコミットを作らず、直前のコミットに入れる（ecobuild task commit --amend）"}},
        {"id": "message", "part": "text-input", "props": {"title": "コミットの文", "placeholder": "何を変えたか"}},
        {"id": "do_commit", "part": "button", "props": {"label": "選んだファイルをコミット", "primary": True}},
        # チェックした変更に（ecobuild task add <ファイル…>・restore <ファイル…> --staged・restore <ファイル…>）
        {"id": "chosen", "layout": "row", "children": ["stage", "unstage", "discard", "source"]},
        {"id": "source", "part": "text-input", "props": {
            "title": "「変更を捨てる」で戻す先（空なら最後のコミット）", "placeholder": "例：HEAD~1 ／ main ／ コミットの番号"}},
        {"id": "stage", "part": "button", "props": {"label": "ステージ", "hint": "チェックした変更を、次のコミットに入れる印を付ける"}},
        {"id": "unstage", "part": "button", "props": {"label": "ステージを取り消す", "hint": "チェックした変更のステージだけを取り消す（中身は残す）"}},
        {"id": "discard", "part": "button", "props": {"label": "変更を捨てる", "hint": "チェックしたファイルを、最後のコミットの状態に戻す"}},
        {"id": "actions", "layout": "row", "children": ["push", "sync", "submit", "stash", "unstash", "open_conflicts", "open_container"]},
        {"id": "open_conflicts", "part": "button", "props": {"label": "衝突を直す…", "hint": "取り込みで衝突したファイルを、どちらの側にするか選ぶ"}},
        {"id": "open_container", "part": "button", "props": {"label": "コンテナ…"}},
        {"id": "stash", "part": "button", "props": {"label": "退避", "hint": "まだコミットしていない変更を、いったんよける"}},
        {"id": "unstash", "part": "button", "props": {"label": "退避を戻す"}},
        {"id": "push", "part": "button", "props": {"label": "Push", "hint": "コミットを GitHub へ送る"}},
        {"id": "sync", "part": "button", "props": {"label": "取り込む", "hint": "作成元の新しいコミットを取り込む"}},
        {"id": "submit", "part": "button", "props": {"label": "提出", "hint": "作成元への取り込みを頼む"}},
        {"id": "tools", "layout": "row", "children": ["build", "test", "clean"]},
        {"id": "build", "part": "button", "props": {"label": "ビルド"}},
        {"id": "test", "part": "button", "props": {"label": "試験"}},
        {"id": "clean", "part": "button", "props": {"label": "クリーン", "hint": "ビルドで作ったものを消す"}},
        {"id": "more", "layout": "row", "children": ["open_build", "open_stashes"]},
        {"id": "open_build", "part": "button", "props": {"label": "ビルド設定・試験を選ぶ…", "hint": "構成・ビルド設定・流す試験・実行の引数を決めて動かす"}},
        {"id": "open_stashes", "part": "button", "props": {"label": "退避の一覧…"}},
        {"id": "out", "part": "output"},
        {"id": "log_title", "part": "note", "props": {"text": "最近のコミット"}},
        {"id": "log", "part": "table", "props": {
            "columns": [{"key": "date", "label": "日時"}, {"key": "author", "label": "だれが"}, {"key": "subject", "label": "何を"}],
            "key": "sha", "empty_text": "コミットはまだありません。",
        }},
    ],
    "bindings": [
        # 読む：status は1回だけ実行され、2つの部品へ出る
        {"read": "status", "args": {"module": {"arg": "module"}}, "to": "state.data"},
        {"read": "status", "args": {"module": {"arg": "module"}}, "to": "changes.status"},
        {"read": "log", "args": {"module": {"arg": "module"}, "count": 10}, "to": "log.rows"},
        {"on": "reload.pressed", "refresh": True},
        # 選ぶ・文を書く
        {"on": "changes.changed", "set": {"paths": {"payload": "paths"}}},
        {"on": "changes.selected", "set": {"file": {"payload": "path"}}},
        {"read": "diff", "args": {"module": {"arg": "module"}, "paths": [{"value": "file"}]}, "to": "diff.text"},
        {"value": "paths", "to": "changes.checked"},
        {"on": "message.changed", "set": {"message": {"payload": "text"}}},
        {"on": "amend.changed", "set": {"amend": {"payload": "on"}}},
        {"value": "amend", "to": "amend.on"},
        {"on": "source.changed", "set": {"restore_source": {"payload": "text"}}},
        # ecobuild のコマンド（人が打つのと同じ：ecobuild task commit <ファイル…> --message <文> [--amend]）
        {"on": "do_commit.pressed", "run": "task commit",
         "args": {"module": {"arg": "module"}, "paths": {"value": "paths"}, "message": {"value": "message"}, "amend": {"value": "amend"}},
         "set": {"paths": None, "amend": None}},
        # チェックした変更に（1つもチェックしていなければ押せない：require）。restore [--staged] [--source <コミット>]
        {"on": "stage.pressed", "run": "task add", "args": {"module": {"arg": "module"}, "paths": {"value": "paths"}}, "require": ["paths"]},
        {"on": "unstage.pressed", "run": "restore", "args": {"module": {"arg": "module"}, "paths": {"value": "paths"}, "staged": True},
         "require": ["paths"]},
        {"on": "discard.pressed", "run": "restore",
         "args": {"module": {"arg": "module"}, "paths": {"value": "paths"}, "source": {"value": "restore_source"}},
         "require": ["paths"], "set": {"paths": None}},
        {"on": "push.pressed", "run": "task push", "args": {"module": {"arg": "module"}}},
        {"on": "sync.pressed", "run": "sync", "args": {"module": {"arg": "module"}}},
        {"on": "submit.pressed", "run": "task submit", "args": {"module": {"arg": "module"}}},
        {"on": "stash.pressed", "run": "stash", "args": {"module": {"arg": "module"}}},
        {"on": "unstash.pressed", "run": "stash pop", "args": {"module": {"arg": "module"}}},
        # ビルド・試験：動かした道具の出力を、続けて出す
        {"on": "build.pressed", "run": "build", "args": {"module": {"arg": "module"}}, "output": "out.lines"},
        {"on": "test.pressed", "run": "test", "args": {"module": {"arg": "module"}}, "output": "out.lines"},
        {"on": "clean.pressed", "run": "clean", "args": {"module": {"arg": "module"}}, "output": "out.lines"},
        # 細かく決めて動かす画面・退避の一覧（この作業空間の窓として開く）
        {"on": "open_build.pressed", "open": "build", "args": {"module": {"arg": "module"}}},
        {"on": "open_conflicts.pressed", "open": "conflicts", "args": {"module": {"arg": "module"}}},
        {"on": "open_container.pressed", "open": "container", "args": {"module": {"arg": "module"}}},
        {"on": "open_stashes.pressed", "open": "stashes", "args": {"module": {"arg": "module"}}},
    ],
}
