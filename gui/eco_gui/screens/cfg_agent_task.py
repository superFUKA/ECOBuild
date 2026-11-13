"""エージェント › 新しいタスクを作る（入力の窓）：エージェントの設定を変えるためのタスクと作業空間を作り、コミットする場所に選ぶ。

人が打つのと同じ：ecobuild task new <題名> --start --name <名前>。作ったら、外の窓の「コミットするタスクブランチ」をその作業空間にする。
"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "新しいタスクを作る", "width": 560, "height": 380},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "新しいタスクを作る", "ok": "作る",
            "intro": "エージェントの設定はリポジトリのファイルなので、タスクブランチでコミットします（提出して取り込まれると効きます）。"
                     "そのためのタスクと作業空間を作ります。",
            "fields": [
                {"name": "title", "label": "新しいタスクの題名", "required": True, "value": "エージェントの設定を変える"},
                {"name": "name", "label": "タスクブランチの名前（task/<番号>-<名前>）", "required": True, "value": "エージェントの設定"},
            ]}},
    ],
    "bindings": [
        {"on": "form.submitted", "run": "task new", "require": ["title", "name"],
         "args": {"module": {"arg": "module"}, "title": {"payload": "values.title"}, "start": True, "name": {"payload": "values.name"}},
         "notify": "タスク #{task.number} の作業空間を作りました。", "close": True,
         "parent": {"agent_place": {"result": "task_branch.workspace"}, "place": {"result": "task_branch.workspace"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
