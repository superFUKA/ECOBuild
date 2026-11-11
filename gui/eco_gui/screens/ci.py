"""モジュール › CI：設定のカード、実行の表（ブランチで絞る・ログ・再実行）、シークレットの一覧。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "CI", "width": 1280, "height": 820, "refresh": {"focus": True, "every": 180}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "section", "body"]},
        {"id": "section", "screen": "mod-tabs", "args": {"current": "ci", "module": {"arg": "module"}}},
        {"id": "nav", "screen": "menu", "args": {"current": "overview", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "モジュール", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        {"id": "body", "layout": "column", "look": "mod-narrow", "children": ["config_title", "config", "config_note", "runs", "secrets_title", "secrets"]},
        {"id": "config_title", "part": "note", "props": {"text": "設定", "tone": "section"}},
        {"id": "config", "part": "mod-ci-config"},
        {"id": "config_note", "part": "note", "props": {
            "text": "手元でコミット・提出等のときに確かめることは「パイプライン」で決めます。", "tone": "muted"}},
        {"id": "runs", "part": "mod-runs"},
        {"id": "secrets_title", "part": "note", "props": {"text": "シークレット", "tone": "section"}},
        {"id": "secrets", "part": "mod-secrets"},
    ],
    "bindings": [
        {"read": "ci show", "args": {"module": {"arg": "module"}}, "to": "config.data"},
        # 実行：すべてのブランチのもの。ブランチで絞っているあいだは、そのブランチのもの（ecobuild ci status --branch <ブランチ>）
        {"read": "ci status", "args": {"module": {"arg": "module"}, "all": True, "count": 30}, "to": "runs.rows"},
        {"read": "ci status", "args": {"module": {"arg": "module"}, "branch": {"value": "ci_branch"}, "count": 30}, "require": ["branch"],
         "to": "runs.branch_rows"},
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "runs.branches"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "runs.url", "from": "url"},
        {"read": "ci secret list", "args": {"module": {"arg": "module"}}, "to": "secrets.names"},
        {"on": "runs.branch", "set": {"ci_branch": {"payload": "name"}}},
        {"value": "ci_branch", "to": "runs.branch"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "config.reload", "refresh": True},
        {"on": "runs.reload", "refresh": True},
        # 設定を変える・やめる：入力の窓（今の設定が初めの値）
        {"on": "config.action", "when": {"action": "init"}, "open": "mod-ci-init", "inside": True, "args": {
            "module": {"arg": "module"}, "os": {"payload": "os"}, "configuration": {"payload": "configuration"},
            "shared": {"payload": "shared"}, "branches": {"payload": "branches"}}},
        {"on": "config.action", "when": {"action": "remove"}, "open": "mod-ci-remove", "inside": True, "args": {"module": {"arg": "module"}}},
        # 実行の行
        {"on": "runs.action", "when": {"action": "logs"}, "open": "mod-ci-log", "inside": True,
         "args": {"module": {"arg": "module"}, "run": {"payload": "run"}}},
        {"on": "runs.action", "when": {"action": "rerun"}, "run": "ci rerun", "args": {"module": {"arg": "module"}, "run": {"payload": "run"}},
         "notify": "もう一度実行しました。少しすると一覧に出ます。"},
        {"on": "runs.action", "when": {"action": "rerun_failed"}, "run": "ci rerun",
         "args": {"module": {"arg": "module"}, "run": {"payload": "run"}, "failed": True}, "notify": "失敗したジョブをもう一度実行しました。"},
        {"on": "runs.dispatch", "open": "mod-ci-run", "inside": True, "args": {"module": {"arg": "module"}, "branch": {"payload": "branch"}}},
        {"on": "secrets.removed", "run": "ci secret remove", "args": {"module": {"arg": "module"}, "name": {"payload": "name"}},
         "notify": "シークレットを削除しました。"},
    ],
}
