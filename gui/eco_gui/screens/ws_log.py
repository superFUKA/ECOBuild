"""作業空間 › ログ：コミットの一覧（左）と、選んだコミットの変更（右。ファイルごとに畳む）。

作業空間の窓の「ログ」のタブに置く。ファイル・フォルダーのログは、同じ画面を別の窓で開く（paths に、見るパスを渡す）。"""

ARGS = {"module": ".", "paths": []}  # 作業空間のフォルダー・見るファイルやフォルダー（空なら全部）

SCREEN = {
    "root": "page",
    "window": {"title": "ログ", "width": 1180, "height": 780},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-log", "children": ["body"]},
        {"id": "body", "layout": "split", "props": {"direction": "row", "sizes": [380, None]}, "children": ["list", "detail"]},
        {"id": "list", "part": "ws-log", "look": "ws-fill"},
        {"id": "detail", "part": "ws-diff", "look": "ws-fill", "props": {"fill": True, "empty_text": "コミットを選ぶと、その変更が出ます。"}},
    ],
    "bindings": [
        {"read": "log", "args": {"module": {"arg": "module"}, "paths": {"arg": "paths"}, "count": {"value": "log_count"},
                                 "branch": {"value": "log_branch"}}, "to": "list.commits"},
        # どのブランチのログを見るか（選ばなければ、今のブランチ。取り出さずに読む：ecobuild log --branch）
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "list.branches"},
        # 戻す操作（この版の状態に戻す・ここまで戻す）は、タスクブランチでだけ（ほかでは灰色と理由）
        {"read": "status", "args": {"module": {"arg": "module"}}, "to": "list.status"},
        {"on": "list.branch", "set": {"log_branch": {"payload": "name"}, "log_commit": None}},
        {"value": "log_branch", "to": "list.branch"},
        {"value": "log_count", "to": "list.count"},
        {"on": "list.more", "set": {"log_count": {"payload": "count"}}},
        {"on": "list.selected", "set": {"log_commit": {"payload": "sha"}}},
        {"value": "log_commit", "to": "list.selected"},
        {"value": "log_commit", "to": "detail.sha"},
        {"read": "show", "args": {"module": {"arg": "module"}, "commit": {"value": "log_commit"}}, "require": ["commit"], "to": "detail.text"},
        # コミットの操作：変更を別に開く／ファイルをその版の状態に戻す（restore --source）／タスクブランチをそこまで戻す（task reset。タスクブランチで）。
        # 戻す操作は、確かめてから（ecobuild の重さのとおり）
        {"on": "list.action", "when": {"name": "show"}, "run": "show", "args": {"module": {"arg": "module"}, "commit": {"payload": "sha"}, "gui": True},
         "instead": {"when": {"code": ["tool_missing", "revision_not_found"]}, "open": "ws-show", "args": {"module": {"arg": "module"}, "commit": {"payload": "sha"}}, "inside": True}},
        {"on": "list.action", "when": {"name": "restore"}, "run": "restore", "args": {"module": {"arg": "module"}, "source": {"payload": "sha"}},
         "notify": "その版の状態に戻しました。内容を確かめてコミットしてください。"},
        {"on": "list.action", "when": {"name": "reset"}, "run": "task reset", "args": {"module": {"arg": "module"}, "commit": {"payload": "sha"}},
         "notify": "そのコミットまで戻しました。"},
    ],
}
