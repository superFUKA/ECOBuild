"""モジュール › 日程：予定の帯・次にやるタスク・期限・スプリント・マイルストーン・担当ごとの量。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "日程", "width": 1280, "height": 820},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "views"]},
        {"id": "nav", "screen": "menu", "args": {"current": "schedule", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "日程", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "views", "layout": "tabs", "props": {"labels": ["予定", "次にやる", "期限", "スプリント", "マイルストーン", "担当ごとの量"]},
         "children": ["timeline", "next", "due", "sprint", "milestones", "workload"]},
        # 予定：開始予定〜終了予定の帯と、期限の印
        {"id": "timeline", "part": "timeline", "props": {"empty_text": "開いているタスクはありません。"}},
        # 次にやる：順番と理由は ecobuild が決める
        {"id": "next", "part": "table", "props": {
            "columns": [{"key": "task.number", "label": "#"}, {"key": "task.title", "label": "題名"}, {"key": "reasons", "label": "理由"},
                        {"key": "task.priority", "label": "優先度"}, {"key": "task.due", "label": "期限"},
                        {"key": "task.estimate", "label": "見積もり"}, {"key": "task.sprint", "label": "スプリント"},
                        {"key": "task.assignees", "label": "担当"}],
            "key": "task.number", "numbered": True, "actions": [{"name": "open", "label": "詳細"}],
            "empty_text": "着手できるタスクはありません。",
        }},
        # 期限：切れたものと、近いもの
        {"id": "due", "layout": "column", "children": ["overdue_title", "overdue", "soon_title", "soon"]},
        {"id": "overdue_title", "part": "note", "props": {"text": "期限切れ"}},
        {"id": "overdue", "part": "table", "props": {
            "columns": [{"key": "number", "label": "#"}, {"key": "title", "label": "題名"}, {"key": "due", "label": "期限"},
                        {"key": "assignees", "label": "担当"}],
            "key": "number", "actions": [{"name": "open", "label": "詳細"}], "empty_text": "期限切れのタスクはありません。",
        }},
        {"id": "soon_title", "part": "note", "props": {"text": "期限が近い（7日以内）"}},
        {"id": "soon", "part": "table", "props": {
            "columns": [{"key": "number", "label": "#"}, {"key": "title", "label": "題名"}, {"key": "due", "label": "期限"},
                        {"key": "assignees", "label": "担当"}],
            "key": "number", "actions": [{"name": "open", "label": "詳細"}], "empty_text": "期限が近いタスクはありません。",
        }},
        # スプリント：一覧と、選んだスプリント（選ばなければ今のスプリント）の進み具合
        {"id": "sprint", "layout": "column", "children": ["sprints", "sprint_title", "sprint_range", "sprint_state", "sprint_tasks"]},
        {"id": "sprints", "part": "table", "props": {
            "columns": [{"key": "name", "label": "スプリント"}, {"key": "start", "label": "始まり"}, {"key": "end", "label": "終わり"}],
            "key": "name", "actions": [{"name": "show", "label": "進み具合"}], "empty_text": "スプリントはまだありません。",
        }},
        {"id": "sprint_title", "part": "note", "props": {"text": "進み具合（選ばなければ、今のスプリント）"}},
        {"id": "sprint_range", "part": "facts", "props": {
            "items": [{"key": "name", "label": "スプリント"}, {"key": "start", "label": "始まり"}, {"key": "end", "label": "終わり"}]}},
        {"id": "sprint_state", "part": "facts", "props": {
            "items": [{"key": "days_left", "label": "残りの日数"}, {"key": "done", "label": "完了"}, {"key": "total", "label": "全体"},
                      {"key": "estimate_done", "label": "完了した見積もり"}, {"key": "estimate_remaining", "label": "見積もりの残り"},
                      {"key": "estimate_total", "label": "見積もりの合計"}]}},
        {"id": "sprint_tasks", "part": "table", "props": {
            "columns": [{"key": "number", "label": "#"}, {"key": "title", "label": "題名"}, {"key": "stage", "label": "段階"},
                        {"key": "estimate", "label": "見積もり"}, {"key": "assignees", "label": "担当"}],
            "key": "number", "actions": [{"name": "open", "label": "詳細"}],
            "labels": {"stage": {"planned": "計画中", "todo": "未着手", "in_progress": "作業中", "in_review": "レビュー待ち", "done": "完了"}},
            "empty_text": "このスプリントのタスクはありません。",
        }},
        # マイルストーン・担当ごとの量
        {"id": "milestones", "part": "table", "props": {
            "columns": [{"key": "title", "label": "マイルストーン"}, {"key": "due", "label": "期日"}, {"key": "done", "label": "完了"},
                        {"key": "total", "label": "全体"}, {"key": "estimate_remaining", "label": "見積もりの残り"},
                        {"key": "overdue_tasks", "label": "期限切れのタスク"}, {"key": "late", "label": "遅れ"}],
            "key": "title", "labels": {"late": {"true": "過ぎている", "false": ""}},
            "empty_text": "マイルストーンに入っているタスクはありません。",
        }},
        {"id": "workload", "part": "table", "props": {
            "columns": [{"key": "assignee", "label": "担当"}, {"key": "open", "label": "開いている"}, {"key": "in_progress", "label": "作業中"},
                        {"key": "estimate_remaining", "label": "見積もりの残り"}, {"key": "overdue", "label": "期限切れ"}],
            "key": "assignee", "labels": {"assignee": {"": "（担当なし）"}}, "empty_text": "開いているタスクはありません。",
        }},
    ],
    "bindings": [
        {"read": "task list", "args": {"module": {"arg": "module"}}, "to": "timeline.rows"},
        {"read": "task next", "args": {"module": {"arg": "module"}, "count": 10}, "to": "next.rows"},
        {"read": "task overdue", "args": {"module": {"arg": "module"}, "days": 7}, "to": "overdue.rows", "from": "overdue"},
        {"read": "task overdue", "args": {"module": {"arg": "module"}, "days": 7}, "to": "soon.rows", "from": "soon"},
        {"read": "sprint list", "args": {"module": {"arg": "module"}}, "to": "sprints.rows"},
        {"read": "sprint status", "args": {"module": {"arg": "module"}, "name": {"value": "sprint"}}, "to": "sprint_range.data", "from": "sprint"},
        {"read": "sprint status", "args": {"module": {"arg": "module"}, "name": {"value": "sprint"}}, "to": "sprint_state.data"},
        {"read": "sprint status", "args": {"module": {"arg": "module"}, "name": {"value": "sprint"}}, "to": "sprint_tasks.rows", "from": "tasks"},
        {"read": "milestone status", "args": {"module": {"arg": "module"}}, "to": "milestones.rows"},
        {"read": "task workload", "args": {"module": {"arg": "module"}}, "to": "workload.rows"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "sprints.action", "set": {"sprint": {"payload": "id"}}},
        # どの並びからも、タスクの詳細を開ける
        {"on": "timeline.selected", "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "here": True},
        {"on": "next.action", "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "here": True},
        {"on": "overdue.action", "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "here": True},
        {"on": "soon.action", "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "here": True},
        {"on": "sprint_tasks.action", "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "here": True},
    ],
}
