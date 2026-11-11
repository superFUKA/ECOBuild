"""作業空間 › 取り込む：どのブランチの、どのバージョンまでを、このタスクブランチへ取り込むかを選ぶ（窓の中に重ねて開く）。

作成元の最新をそのまま取り込むか、ブランチを選んで、そのコミット（新しい順）から取り込むところを選ぶ
（ecobuild sync ／ ecobuild sync --from-branch <ブランチ> --at <コミット>）。取り込んだコミットは、このタスクブランチの提出にも入る。"""

ARGS = {"module": "."}  # 作業空間のフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "取り込む", "width": 760, "height": 720},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["title", "now", "latest_row", "pick_title", "branch", "versions", "foot"]},
        {"id": "title", "part": "note", "props": {"text": "取り込む", "heading": True}},
        {"id": "now", "part": "facts", "props": {"items": [
            {"key": "branch", "label": "このタスクブランチ"}, {"key": "base", "label": "作成元"}, {"key": "base_at", "label": "取り込み済みの版"},
            {"key": "base_behind", "label": "作成元の新しいコミット"}]}},
        {"id": "latest_row", "layout": "row", "look": "tools", "children": ["latest"]},
        {"id": "latest", "part": "button", "props": {"label": "作成元の最新を取り込む", "primary": True, "hint": "ecobuild sync"}},
        {"id": "pick_title", "part": "note", "props": {"tone": "section", "text": "バージョン・ブランチを選んで取り込む"}},
        {"id": "branch", "part": "select-rows", "props": {"title": "ブランチ（GitHub にあるもの。作成元のほかを選ぶと、作成元の最新も一緒に取り込みます）",
                                                          "value_key": "name", "none_label": "（選んでください）"}},
        {"id": "versions", "part": "ws-log", "props": {"mode": "plain", "short": True, "empty_text": "ブランチを選ぶと、そのコミットが新しい順に出ます。"}},
        {"id": "foot", "layout": "row", "look": "actions", "children": ["cancel", "take"]},
        {"id": "cancel", "part": "button", "props": {"label": "キャンセル"}},
        {"id": "take", "part": "button", "props": {"label": "選んだバージョンまで取り込む", "hint": "ecobuild sync --from-branch <ブランチ> --at <コミット>"}},
    ],
    "bindings": [
        {"read": "status", "args": {"module": {"arg": "module"}, "fetch": True}, "to": "now.data"},
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "branch.rows"},
        {"on": "branch.changed", "set": {"sync_branch": {"payload": "value"}, "sync_at": None}},
        {"value": "sync_branch", "to": "branch.value"},
        {"read": "log", "args": {"module": {"arg": "module"}, "branch": {"value": "sync_branch"}, "count": 50}, "require": ["branch"], "to": "versions.commits"},
        {"on": "versions.selected", "set": {"sync_at": {"payload": "sha"}}},
        {"value": "sync_at", "to": "versions.selected"},
        {"on": "latest.pressed", "run": "sync", "args": {"module": {"arg": "module"}}, "notify": "取り込みました。", "close": True},
        {"on": "take.pressed", "run": "sync",
         "args": {"module": {"arg": "module"}, "from_branch": {"value": "sync_branch"}, "at": {"value": "sync_at"}}, "require": ["from_branch", "at"],
         "notify": "取り込みました。", "close": True},
        {"on": "cancel.pressed", "close": True},
    ],
}
