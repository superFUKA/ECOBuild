"""ハブ：この PC にあるモジュールの一覧。選ぶと、そのモジュールの窓を開く。

読むのは、開いたとき・変える操作の後・「読み直す」を押したとき。窓が前に来るたびには読み直さない
（GitHub に聞く読み：module list --all・installer check が、そのたびに走るため。今までの GUI と同じ）。
"""

SCREEN = {
    "root": "page",
    "window": {"title": "ECOBuild Hub", "width": 1000, "height": 720, "refresh": {"focus": True}},  # 戻ってきたら読み直す（端末で足したモジュール等）
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "nav", "screen": "hub-menu", "args": {"current": "hub"}},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "setup", "update", "modules"]},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload", "add"]},
        {"id": "title", "part": "note", "props": {"text": "モジュール一覧", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        {"id": "add", "part": "button", "props": {"label": "＋ モジュール追加", "primary": True}},
        # 上の帯：開発の環境が足りないとき・ECOBuild の新しい版があるときだけ出る
        {"id": "setup", "part": "hub-setup-banner"},
        {"id": "update", "part": "hub-update"},
        {"id": "modules", "part": "hub-modules"},
    ],
    "bindings": [
        {"read": "workspace list", "to": "modules.rows", "from": "modules"},
        {"read": "workspace list", "to": "modules.legacy", "from": "legacy"},
        {"read": "doctor", "lazy": True, "to": "setup.items", "from": "items"},  # 遅い（数十秒）：戻ってくるたびには読まない
        # GitHub に聞くもの（遅い）は後から：アーカイブ済みか・型、新しい版があるか
        {"read": "module list", "args": {"all": True}, "lazy": True, "to": "modules.known"},
        {"read": "installer check", "lazy": True, "to": "update.check"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "setup.pressed", "open": "hub-settings", "here": True},
        {"on": "update.pressed", "run": "gui update", "notify": "{message}"},  # installer update の後、GUI を起動し直す
        # 足す：窓の中に、入力の窓を重ねる
        {"on": "add.pressed", "open": "hub-add", "inside": True},
        {"on": "modules.add", "open": "hub-add", "inside": True},
        # 選んだモジュールの窓を開く（最初は作業空間。モジュールごとに1つ。開いていれば、今のページのまま前に出る）
        {"on": "modules.action", "when": {"action": "open"}, "open": "frame-workspaces", "args": {"module": {"payload": "id"}}, "keep": True},
        # カードのメニュー：エクスプローラー（ecobuild open --app explorer）・Visual Studio（open --app vs --solution。
        # ソリューションがまだなければ「ビルドしてから開きますか？」）・ショートカット（ecobuild gui shortcut --module … --pick）
        {"on": "modules.action", "when": {"action": "explorer"}, "run": "open", "args": {"module": {"payload": "id"}, "app": "explorer"}},
        {"on": "modules.action", "when": {"action": "vs"}, "run": "open", "args": {"module": {"payload": "id"}, "app": "vs", "solution": True},
         "notify": "Visual Studio {version} で開きます：{name}",
         "instead": {"when": {"code": "no_solution"}, "open": "frame-vs-build", "inside": True, "args": {"module": {"payload": "id"}, "version": ""}}},
        {"on": "modules.action", "when": {"action": "shortcut"}, "run": "gui shortcut", "args": {"module": {"payload": "id"}, "pick": True},
         "notify": "{message}"},
        # 使えない（clone でなくなった等）：理由と、フォルダを開く・一覧から外す
        {"on": "modules.action", "when": {"action": "unusable"}, "open": "hub-unusable", "inside": True,
         "args": {"path": {"payload": "id"}, "name": {"payload": "name"}, "reason": {"payload": "reason"}}},
        # 一覧から外す：理由（フォルダがない等）と、残るものを見せてから（ecobuild workspace forget <フォルダー>）
        {"on": "modules.action", "when": {"action": "forget"}, "open": "hub-forget", "inside": True,
         "args": {"path": {"payload": "id"}, "name": {"payload": "name"}, "reason": {"payload": "reason"}}},
        # 片付ける：まずアーカイブ（読み取り専用）。解除・削除は「アーカイブ済み」から（ecobuild module archive <所有者/名前>）
        {"on": "modules.action", "when": {"action": "away"}, "run": "module archive", "args": {"name": {"payload": "repository"}},
         "notify": "アーカイブしました（読み取り専用）。「アーカイブ済み」に移動しました。"},
        {"on": "modules.archived", "when": {"action": "unarchive"}, "run": "module unarchive", "args": {"name": {"payload": "repository"}},
         "notify": "アーカイブを解除しました。"},
        {"on": "modules.archived", "when": {"action": "folder"}, "run": "open", "args": {"module": {"payload": "folder"}, "app": "explorer"}},
        {"on": "modules.archived", "when": {"action": "delete"}, "open": "hub-delete", "inside": True,
         "args": {"repository": {"payload": "repository"}, "local": {"payload": "local"}}},
        # 前の版の作業空間（ecobuild workspace close <フォルダー>・workspace forget <フォルダー>）
        {"on": "modules.legacy", "when": {"action": "folder"}, "run": "open", "args": {"module": {"payload": "path"}, "app": "explorer"}},
        {"on": "modules.legacy", "when": {"action": "close"}, "run": "workspace close", "args": {"path": {"payload": "path"}},
         "notify": "前の作業空間を閉じました。"},
        {"on": "modules.legacy", "when": {"action": "forget"}, "run": "workspace forget", "args": {"path": {"payload": "path"}},
         "notify": "一覧から外しました。"},
    ],
}
