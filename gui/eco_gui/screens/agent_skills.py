"""モジュール › エージェント › スキル：モジュールのスキル（必要なときにエージェントが読む手順・知識）。一覧・中身・足す・変える・消す。"""

ARGS = {"module": "."}  # モジュールのフォルダー（変えるときは、タスクブランチの作業空間）

SCREEN = {
    "root": "page",
    "window": {"title": "エージェントのスキル", "width": 980, "height": 820},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "sub", "head", "where", "list", "selected", "info", "tabs"]},
        {"id": "nav", "screen": "menu", "args": {"current": "agents", "module": {"arg": "module"}}},
        {"id": "sub", "screen": "agents-menu", "args": {"current": "agent-skills", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "スキル", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "where", "part": "note", "props": {"text": "スキルは、必要なときにエージェントが読む手順・知識です（ツールは増えません）。足す・変える・消すは、タスクブランチの作業空間で実行するとコミットされ、提出して取り込まれると、役の「使えるスキル」に合うものがエージェントに渡ります。"}},
        {"id": "list", "part": "table", "props": {
            "columns": [{"key": "name", "label": "名前"}, {"key": "description", "label": "説明"}, {"key": "used_by", "label": "使える役"},
                        {"key": "pending", "label": "状態"}],
            "key": "name",
            "actions": [{"name": "show", "label": "見る"}, {"name": "to_preset", "label": "このPCのスキルにする"}, {"name": "remove", "label": "消す"}],
            "labels": {"pending": {"true": "まだ渡らない", "false": ""}},
            "empty_text": "このモジュールにスキルはありません。",
        }},
        {"id": "selected", "part": "note", "props": {"prefix": "選んでいるスキル："}},
        {"id": "info", "part": "facts", "props": {
            "items": [{"key": "description", "label": "説明"}, {"key": "used_by", "label": "使える役"},
                      {"key": "files", "label": "ほかのファイル"}, {"key": "folder", "label": "置き場所"}],
        }},
        {"id": "tabs", "layout": "tabs", "props": {"labels": ["本文", "変える", "足す"]}, "children": ["document", "edit", "add"]},
        {"id": "document", "part": "text-view", "props": {"empty_text": "「見る」で、スキルの本文（SKILL.md）が出ます。"}},
        # 変える（ecobuild agent skill set <名前> --description <説明>）
        {"id": "edit", "layout": "column", "children": ["edit_note", "e_description", "save"]},
        {"id": "edit_note", "part": "note", "props": {"text": "説明は、何をするか・いつ使うか（エージェントはこれを見て、読むかを決めます）。本文は、ここでは変えられません（ecobuild agent skill set <名前> --document <ファイル>）。"}},
        {"id": "e_description", "part": "text-area", "props": {"title": "説明", "rows": 4}},
        {"id": "save", "part": "button", "props": {"label": "保存してコミット", "primary": True}},
        # 足す（ecobuild agent skill add <名前> --description … / --from-preset … / --from-dir …）
        {"id": "add", "layout": "column", "children": ["add_names", "new_description", "do_add"]},
        {"id": "add_names", "layout": "row", "children": ["new_name", "new_from", "new_dir"]},
        {"id": "new_name", "part": "text-input", "props": {"title": "名前（英小文字・数字・-）", "placeholder": "例：release-notes"}},
        {"id": "new_from", "part": "select-rows", "props": {"title": "写すこのPCのスキル", "none_label": "（写さない）"}},
        {"id": "new_dir", "part": "text-input", "props": {"title": "取り込むフォルダー（SKILL.md がある）", "placeholder": "例：C:\\Users\\me\\.claude\\skills\\pdf"}},
        {"id": "new_description", "part": "text-area", "props": {"title": "説明（新しく作るとき。何をするか・いつ使うか）", "rows": 3}},
        {"id": "do_add", "part": "button", "props": {"label": "＋ 足す", "primary": True}},
    ],
    "bindings": [
        {"read": "agent skill list", "args": {"module": {"arg": "module"}}, "to": "list.rows"},
        {"read": "agent skill preset list", "args": {"module": {"arg": "module"}}, "to": "new_from.rows"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "list.action", "when": {"action": "show"}, "set": {"skill": {"payload": "id"}}},
        {"value": "skill", "to": "selected.text"},
        {"read": "agent skill show", "args": {"module": {"arg": "module"}, "name": {"value": "skill"}}, "to": "info.data"},
        {"read": "agent skill show", "args": {"module": {"arg": "module"}, "name": {"value": "skill"}}, "to": "document.text", "from": "document"},
        {"read": "agent skill show", "args": {"module": {"arg": "module"}, "name": {"value": "skill"}}, "to": "e_description.text", "from": "description"},
        # 行のボタン（ecobuild agent skill preset add <名前> --from-module <名前>・ecobuild agent skill remove <名前>）
        {"on": "list.action", "when": {"action": "to_preset"}, "run": "agent skill preset add",
         "args": {"module": {"arg": "module"}, "name": {"payload": "id"}, "from_module": {"payload": "id"}}},
        {"on": "list.action", "when": {"action": "remove"}, "run": "agent skill remove",
         "args": {"module": {"arg": "module"}, "name": {"payload": "id"}}, "set": {"skill": None}},
        # 変える
        {"on": "e_description.changed", "set": {"skill_description": {"payload": "text"}}},
        {"on": "save.pressed", "run": "agent skill set",
         "args": {"module": {"arg": "module"}, "name": {"value": "skill"}, "description": {"value": "skill_description"}},
         "set": {"skill_description": None}},
        # 足す
        {"on": "new_name.changed", "set": {"skill_new_name": {"payload": "text"}}},
        {"on": "new_from.changed", "set": {"skill_new_from": {"payload": "value"}}},
        {"value": "skill_new_from", "to": "new_from.value"},
        {"on": "new_dir.changed", "set": {"skill_new_dir": {"payload": "text"}}},
        {"on": "new_description.changed", "set": {"skill_new_description": {"payload": "text"}}},
        {"on": "do_add.pressed", "run": "agent skill add",
         "args": {"module": {"arg": "module"}, "name": {"value": "skill_new_name"}, "description": {"value": "skill_new_description"},
                  "from_preset": {"value": "skill_new_from"}, "from_dir": {"value": "skill_new_dir"}},
         "set": {"skill": {"value": "skill_new_name"}}},
    ],
}
