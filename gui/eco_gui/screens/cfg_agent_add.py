"""エージェントを追加（入力の窓）：プリセットから作るか、新しく作る。エージェントの画面から、窓の中に重ねて開く。"""

ARGS = {"module": ".", "place": ""}  # モジュールのフォルダー・コミットするタスクブランチの作業空間（初めの値）

SCREEN = {
    "root": "page",
    "window": {"title": "エージェントを追加", "width": 560, "height": 640},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "エージェントを追加", "ok": "追加",
            "intro": "このモジュールのエージェント（役）を足します。保存するとリポジトリにコミットし、提出して取り込まれると起動できます。",
            "initial": {"place": {"arg": "place"}},
            "fields": [
                {"name": "how", "label": "作り方", "type": "radio", "value": "preset", "options": [
                    {"value": "preset", "label": "プリセットから作成", "help": "プリセットを写して、名前を付けて足します"},
                    {"value": "new", "label": "新規作成", "help": "空の役を作ります（文書・ツールは後で）"}]},
                {"name": "from_preset", "label": "元にするプリセット", "type": "select", "show_if": {"how": "preset"},
                 "options_from": {"value": "name", "label": "title", "note": ["name", "source"],
                                  "note_labels": {"sample": "見本", "preset": "このPCのプリセット", "module": "モジュールの登録"}}},
                {"name": "name", "label": "名前（英小文字・数字・-・_）", "placeholder": "例：reviewer", "required": True,
                 "help": "プリセットから作るときは、空ならプリセットと同じ名前", "empty_uses": "from_preset"},
                {"name": "title", "label": "表示名", "placeholder": "例：レビュー役", "show_if": {"how": "new"}},
                {"name": "human_start", "label": "人が手で起動できる（作業空間の「エージェント」の ＋ に出る）", "type": "checkbox", "value": True},
                {"name": "no_owner_tools", "label": "コミット・push・提出はさせない（変えたファイルは人が見て、人がコミット・提出する）",
                 "type": "checkbox", "value": True},
                {"name": "place", "label": "コミットするタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）"},
            ],
        }},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        {"read": "agent preset list", "args": {"module": {"arg": "module"}}, "to": "form.rows"},
        {"on": "form.cancelled", "close": True},
        # ecobuild agent registry add <名前> [--from-preset <プリセット>] [--title …] --human-start/--no-human-start [--no-owner-tools]
        {"on": "form.submitted", "run": "agent registry add", "confirmed": True, "require": ["module"],
         "parent": {"place": {"payload": "values.place"}},  # 外の窓は、コミットした場所を見せる
         "args": {"module": {"payload": "values.place"}, "name": {"payload": "values.name"}, "from_preset": {"payload": "values.from_preset"},
                  "title": {"payload": "values.title"}, "human_start": {"payload": "values.human_start"},
                  "no_owner_tools": {"payload": "values.no_owner_tools"}},
         "notify": "エージェントを追加してコミットしました。提出して取り込まれると起動できます。", "close": True},
    ],
}
