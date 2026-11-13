"""スキルを追加（入力の窓）：新しく作る・このPCのスキルから写す・フォルダーから取り込む。"""

ARGS = {"module": ".", "place": ""}  # モジュールのフォルダー・コミットするタスクブランチの作業空間（初めの値）

SCREEN = {
    "root": "page",
    "window": {"title": "スキルを追加", "width": 560, "height": 680},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "スキルを追加", "ok": "追加",
            "intro": "このモジュールのスキルを足します。保存するとリポジトリにコミットし、提出して取り込まれるとエージェントに渡ります（役の「使えるスキル」に合うもの）。",
            "initial": {"place": {"arg": "place"}},
            "fields": [
                {"name": "how", "label": "作り方", "type": "radio", "value": "new", "options": [
                    {"value": "new", "label": "新規作成", "help": "説明と本文を書いて作ります"},
                    {"value": "preset", "label": "このPCのスキルから", "help": "このPCのスキルを写します"},
                    {"value": "dir", "label": "フォルダーから取り込む",
                     "help": "SKILL.md のあるフォルダー（Claude Code の個人のスキル ~/.claude/skills/<名前> 等）を、ほかのファイルごと写します"}]},
                {"name": "from_preset", "label": "元にするこのPCのスキル", "type": "select", "show_if": {"how": "preset"},
                 "options_from": {"value": "name", "label": "name", "note": "description"}},
                {"name": "from_dir", "label": "フォルダー", "placeholder": "例：C:/Users/me/.claude/skills/pdf", "show_if": {"how": "dir"}, "required": True},
                {"name": "name", "label": "名前（英小文字・数字・-）", "placeholder": "例：release-notes", "required": True,
                 "help": "このPCのスキルを写すときは、空なら元と同じ名前", "empty_uses": "from_preset"},
                {"name": "description", "label": "説明（何をするか・いつ使うか）", "type": "textarea", "show_if": {"how": "new"},
                 "help": "本文は、足した後に左の一覧から選んで書きます"},
                {"name": "place", "label": "コミットするタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）"},
            ],
        }},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        {"read": "agent skill preset list", "args": {"module": {"arg": "module"}}, "to": "form.rows"},
        {"on": "form.cancelled", "close": True},
        # ecobuild agent skill add <名前> --description … ／ --from-preset … ／ --from-dir …
        {"on": "form.submitted", "run": "agent skill add", "confirmed": True, "require": ["module"],
         "parent": {"place": {"payload": "values.place"}},  # 外の窓は、コミットした場所を見せる
         "args": {"module": {"payload": "values.place"}, "name": {"payload": "values.name"}, "from_preset": {"payload": "values.from_preset"},
                  "from_dir": {"payload": "values.from_dir"}, "description": {"payload": "values.description"}},
         "notify": "スキルを追加してコミットしました。提出して取り込まれると渡ります。", "close": True},
    ],
}
