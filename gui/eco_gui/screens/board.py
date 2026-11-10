"""モジュール › ボード：開いているタスクを、段階ごとの列に並べる。カードから詳細を開き、カードを移して段階を変える。

カードを「計画中」「未着手」へ移すと段階を変え（task edit --stage）、「作業中」へ移すと始め（task start）、「完了」へ移すと閉じる（task close）。
"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "ボード", "width": 1000, "height": 640},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "head", "start_name", "board"]},
        {"id": "nav", "screen": "menu", "args": {"current": "board", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "ボード", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "start_name", "part": "text-input", "props": {
            "title": "「作業中」へ移して始めるときに作る、タスクブランチの名前", "placeholder": "例：login（GitHub にタスクブランチがあるタスクは、空でよい）"}},
        {"id": "board", "part": "board", "props": {
            "columns": [{"key": "planned", "label": "計画中"}, {"key": "todo", "label": "未着手"}, {"key": "in_progress", "label": "作業中"},
                        {"key": "in_review", "label": "レビュー待ち"}, {"key": "done", "label": "完了"}],
            "group": "stage", "key": "number", "title": "title",
            "details": [{"key": "assignees", "label": "担当"}, {"key": "priority", "label": "優先度"}, {"key": "due", "label": "期限"},
                        {"key": "estimate", "label": "見積もり"}, {"key": "sprint", "label": "スプリント"}],
            # 移せる列：計画中・未着手（task edit --stage。作業を始める前だけ）、作業中（task start）、完了（task close）。
            # レビュー待ちへは、作業空間からの提出で進む
            "moves": ["planned", "todo", "in_progress", "done"],
            "empty_text": "開いているタスクはありません。",
        }},
    ],
    "bindings": [
        {"read": "task list", "args": {"module": {"arg": "module"}}, "to": "board.cards"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "board.selected", "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "here": True},
        {"on": "start_name.changed", "set": {"start_name": {"payload": "text"}}},
        {"value": "start_name", "to": "start_name.text"},
        # 移した先の列で、呼ぶコマンドが決まる。計画中・未着手：段階を変える（ecobuild task edit <番号> --stage <段階>）
        {"on": "board.moved", "when": {"to": "planned"}, "run": "task edit",
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "stage": "planned"}},
        {"on": "board.moved", "when": {"to": "todo"}, "run": "task edit",
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "stage": "todo"}},
        # 作業中：始める（ecobuild task start <番号> [--name <名前>]）。完了：閉じる（ecobuild task close <番号>。確かめてから）
        {"on": "board.moved", "when": {"to": "in_progress"}, "run": "task start",
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "name": {"value": "start_name"}}, "set": {"start_name": None}},
        {"on": "board.moved", "when": {"to": "done"}, "run": "task close", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}},
    ],
}
