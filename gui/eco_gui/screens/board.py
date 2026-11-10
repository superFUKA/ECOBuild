"""モジュール › ボード：開いているタスクを、段階ごとの列に並べる。カードから詳細を開き、段階を変える。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "ボード", "width": 1000, "height": 640},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "head", "board"]},
        {"id": "nav", "screen": "menu", "args": {"current": "board", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "ボード", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "board", "part": "board", "props": {
            "columns": [{"key": "planned", "label": "計画中"}, {"key": "todo", "label": "未着手"}, {"key": "in_progress", "label": "作業中"},
                        {"key": "in_review", "label": "レビュー待ち"}, {"key": "done", "label": "完了"}],
            "group": "stage", "key": "number", "title": "title",
            "details": [{"key": "assignees", "label": "担当"}, {"key": "priority", "label": "優先度"}, {"key": "due", "label": "期限"},
                        {"key": "estimate", "label": "見積もり"}, {"key": "sprint", "label": "スプリント"}],
            # task edit --stage で変えられるのは、作業を始める前の段階だけ（その先は、始める・提出・完了で進む）
            "moves": ["planned", "todo"],
            "empty_text": "開いているタスクはありません。",
        }},
    ],
    "bindings": [
        {"read": "task list", "args": {"module": {"arg": "module"}}, "to": "board.cards"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "board.selected", "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "here": True},
        # 段階を変える（ecobuild task edit <番号> --stage <段階>）
        {"on": "board.moved", "run": "task edit", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "stage": {"payload": "to"}}},
    ],
}
