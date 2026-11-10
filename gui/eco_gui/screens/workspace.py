"""作業空間：今のブランチと変更。コミット・Push・取り込み・提出。"""

ARGS = {"module": "."}  # 作業空間のフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "作業空間", "width": 820, "height": 640},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "state", "changes", "commit", "actions", "log_title", "log"]},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": {"arg": "module"}, "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "state", "part": "facts", "props": {"items": [
            {"key": "branch", "label": "ブランチ"}, {"key": "task", "label": "タスク"}, {"key": "base", "label": "作成元"},
            {"key": "ahead", "label": "まだ送っていないコミット"}, {"key": "behind", "label": "まだ取り込んでいないコミット"},
        ]}},
        {"id": "changes", "part": "changes"},
        {"id": "commit", "layout": "row", "children": ["message", "do_commit"]},
        {"id": "message", "part": "text-input", "props": {"title": "コミットの文", "placeholder": "何を変えたか"}},
        {"id": "do_commit", "part": "button", "props": {"label": "選んだファイルをコミット", "primary": True}},
        {"id": "actions", "layout": "row", "children": ["push", "sync", "submit"]},
        {"id": "push", "part": "button", "props": {"label": "Push", "hint": "コミットを GitHub へ送る"}},
        {"id": "sync", "part": "button", "props": {"label": "取り込む", "hint": "作成元の新しいコミットを取り込む"}},
        {"id": "submit", "part": "button", "props": {"label": "提出", "hint": "作成元への取り込みを頼む"}},
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
        {"value": "paths", "to": "changes.checked"},
        {"on": "message.changed", "set": {"message": {"payload": "text"}}},
        # ecobuild のコマンド（人が打つのと同じ：ecobuild task commit <ファイル…> --message <文>）
        {"on": "do_commit.pressed", "run": "task commit",
         "args": {"module": {"arg": "module"}, "paths": {"value": "paths"}, "message": {"value": "message"}}, "set": {"paths": []}},
        {"on": "push.pressed", "run": "task push", "args": {"module": {"arg": "module"}}},
        {"on": "sync.pressed", "run": "sync", "args": {"module": {"arg": "module"}}},
        {"on": "submit.pressed", "run": "task submit", "args": {"module": {"arg": "module"}}},
    ],
}
