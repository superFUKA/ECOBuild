"""モジュール › タスク › 詳細：題・本文・状態・計画の値・コメント。編集・コメント・始める・閉じる・開き直す。"""

ARGS = {"module": ".", "issue": 0}  # モジュールのフォルダーと、タスクの番号

SCREEN = {
    "root": "page",
    "window": {"title": "タスクの詳細", "width": 820, "height": 820},
    "nodes": [
        {"id": "page", "layout": "column", "children": [
            "nav", "head", "state", "plan", "body", "actions", "edit_head", "edit_text", "edit_plan", "edit_people", "save",
            "comments_title", "comments", "comment"]},
        {"id": "nav", "screen": "menu", "args": {"current": "tasks", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "state", "part": "facts", "props": {
            "items": [{"key": "number", "label": "番号"}, {"key": "state", "label": "状態"}, {"key": "assignees", "label": "担当"},
                      {"key": "labels", "label": "ラベル"}, {"key": "milestone", "label": "マイルストーン"},
                      {"key": "branch", "label": "タスクブランチ"}, {"key": "base", "label": "作成元"}],
            "labels": {"state": {"open": "開いている", "closed": "閉じている"}},
        }},
        {"id": "plan", "part": "facts", "props": {
            "items": [{"key": "stage", "label": "段階"}, {"key": "priority", "label": "優先度"}, {"key": "due", "label": "期限"},
                      {"key": "estimate", "label": "見積もり"}, {"key": "sprint", "label": "スプリント"},
                      {"key": "planned_start", "label": "開始予定"}, {"key": "planned_end", "label": "終了予定"}],
            "labels": {"stage": {"planned": "計画中", "todo": "未着手", "in_progress": "作業中", "in_review": "レビュー待ち", "done": "完了"}},
        }},
        {"id": "body", "part": "note"},
        # 始める・閉じる・開き直す
        {"id": "actions", "layout": "row", "children": ["start_name", "start", "close", "reopen"]},
        {"id": "start_name", "part": "text-input", "props": {"title": "「始める」で作るタスクブランチの名前", "placeholder": "例：login"}},
        {"id": "start", "part": "button", "props": {"label": "始める", "hint": "タスクブランチと作業空間を作る"}},
        {"id": "close", "part": "button", "props": {"label": "閉じる"}},
        {"id": "reopen", "part": "button", "props": {"label": "開き直す"}},
        # 編集：変えた欄だけが渡る（空のままの欄は変えない）
        {"id": "edit_head", "part": "note", "props": {"text": "編集（変える欄だけ入れる）"}},
        {"id": "edit_text", "part": "text-input", "props": {"title": "題"}},
        {"id": "edit_plan", "layout": "row", "children": ["edit_stage", "edit_priority", "edit_due", "edit_estimate"]},
        {"id": "edit_stage", "part": "select", "props": {"title": "段階（始める前だけ）", "options": [
            {"value": "", "label": "（変えない）"}, {"value": "planned", "label": "計画中"}, {"value": "todo", "label": "未着手"}]}},
        {"id": "edit_priority", "part": "select", "props": {"title": "優先度", "options": [
            {"value": "", "label": "（変えない）"}, {"value": "High", "label": "High"}, {"value": "Middle", "label": "Middle"},
            {"value": "Low", "label": "Low"}]}},
        {"id": "edit_due", "part": "text-input", "props": {"title": "期限", "placeholder": "YYYY-MM-DD"}},
        {"id": "edit_estimate", "part": "text-input", "props": {"title": "見積もり", "placeholder": "数"}},
        {"id": "edit_people", "layout": "row", "children": ["edit_add_assignee", "edit_remove_assignee", "edit_clear"]},
        {"id": "edit_add_assignee", "part": "text-input", "props": {"title": "加える担当", "placeholder": "例：octocat（@me は自分）"}},
        {"id": "edit_remove_assignee", "part": "text-input", "props": {"title": "外す担当", "placeholder": "例：octocat"}},
        {"id": "edit_clear", "part": "select", "props": {"title": "消す値", "options": [
            {"value": "", "label": "（消さない）"}, {"value": "priority", "label": "優先度"}, {"value": "due", "label": "期限"},
            {"value": "estimate", "label": "見積もり"}]}},
        {"id": "save", "part": "button", "props": {"label": "変更を保存", "primary": True}},
        # コメント
        {"id": "comments_title", "part": "note", "props": {"text": "コメント"}},
        {"id": "comments", "part": "table", "props": {
            "columns": [{"key": "author", "label": "だれが"}, {"key": "body", "label": "コメント"}],
            "key": "author", "empty_text": "コメントはまだありません。",
        }},
        {"id": "comment", "layout": "row", "children": ["message", "do_comment"]},
        {"id": "message", "part": "text-input", "props": {"title": "コメントを書く", "placeholder": "作業の記録・申し送り"}},
        {"id": "do_comment", "part": "button", "props": {"label": "コメント"}},
    ],
    "bindings": [
        # 読む：task status <番号> --body は1回だけ実行され、いくつもの部品へ出る
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "body": True}, "to": "title.text", "from": "title"},
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "body": True}, "to": "state.data"},
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "body": True}, "to": "plan.data", "from": "task"},
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "body": True}, "to": "body.text", "from": "body"},
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "body": True}, "to": "comments.rows", "from": "comments"},
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "body": True}, "to": "edit_text.text", "from": "title"},
        {"on": "reload.pressed", "refresh": True},
        # 始める・閉じる・開き直す（ecobuild task start <番号> --name <名前>・task close <番号>・task reopen <番号>）
        {"on": "start_name.changed", "set": {"start_name": {"payload": "text"}}},
        {"on": "start.pressed", "run": "task start",
         "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}, "name": {"value": "start_name"}}},
        {"on": "close.pressed", "run": "task close", "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}}},
        {"on": "reopen.pressed", "run": "task reopen", "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}}},
        # 編集（ecobuild task edit <番号> --title … --stage … --priority … --due … --estimate … --add-assignee … --remove-assignee … --clear …）
        {"on": "edit_text.changed", "set": {"edit_title": {"payload": "text"}}},
        {"on": "edit_stage.changed", "set": {"edit_stage": {"payload": "value"}}},
        {"on": "edit_priority.changed", "set": {"edit_priority": {"payload": "value"}}},
        {"on": "edit_due.changed", "set": {"edit_due": {"payload": "text"}}},
        {"on": "edit_estimate.changed", "set": {"edit_estimate": {"payload": "text"}}},
        {"on": "edit_add_assignee.changed", "set": {"edit_add_assignee": {"payload": "text"}}},
        {"on": "edit_remove_assignee.changed", "set": {"edit_remove_assignee": {"payload": "text"}}},
        {"on": "edit_clear.changed", "set": {"edit_clear": {"payload": "value"}}},
        {"value": "edit_stage", "to": "edit_stage.value"},
        {"value": "edit_priority", "to": "edit_priority.value"},
        {"value": "edit_clear", "to": "edit_clear.value"},
        {"on": "save.pressed", "run": "task edit",
         "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}, "title": {"value": "edit_title"}, "stage": {"value": "edit_stage"},
                  "priority": {"value": "edit_priority"}, "due": {"value": "edit_due"}, "estimate": {"value": "edit_estimate"},
                  "add_assignee": {"value": "edit_add_assignee"}, "remove_assignee": {"value": "edit_remove_assignee"},
                  "clear": {"value": "edit_clear"}},
         "set": {"edit_title": None, "edit_stage": None, "edit_priority": None, "edit_due": None, "edit_estimate": None,
                 "edit_add_assignee": None, "edit_remove_assignee": None, "edit_clear": None}},
        # コメント（ecobuild task comment <番号> --message <文>）
        {"on": "message.changed", "set": {"message": {"payload": "text"}}},
        {"on": "do_comment.pressed", "run": "task comment",
         "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "message": {"value": "message"}}, "set": {"message": None}},
    ],
}
