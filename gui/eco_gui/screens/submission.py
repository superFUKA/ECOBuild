"""提出：1つのタスクの提出。状態と差分を見て、コメント・確認・承認・差し戻し・取り下げ・取り込み・反映をする。

ボタンは、手元にタスクブランチがあるか（task status の task_branch）で出し分ける：ある（この PC で作業しているタスク）なら
「自分の提出」、ない（ほかの人の提出）なら「ほかの人の提出を見る」。提出がないときは、提出に対する操作を出さない。
"""

ARGS = {"module": ".", "task": ""}  # モジュールのフォルダー・タスクの番号（表の行の ID のまま、文字で受ける。コマンドへは数で渡る）

SCREEN = {
    "root": "page",
    "window": {"title": "提出", "width": 900, "height": 820},
    "nodes": [
        {"id": "page", "layout": "column", "children": [
            "head", "info", "pull_request", "activity", "checks", "reviews", "comments", "diff", "talk",
            "judge_title", "judge", "own_title", "own", "options_title", "options"]},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "提出", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "info", "part": "facts", "props": {"items": [
            {"key": "number", "label": "タスク"}, {"key": "title", "label": "題名"}, {"key": "assignees", "label": "担当"},
            {"key": "branch", "label": "タスクブランチ"}, {"key": "base", "label": "作成元"},
            {"key": "workspace", "label": "手元の作業空間"}, {"key": "commits", "label": "入るコミット"},
        ]}},
        {"id": "pull_request", "part": "facts", "props": {
            "items": [{"key": "state", "label": "提出"}, {"key": "draft", "label": "下書き"}, {"key": "partial", "label": "取り込んだら"},
                      {"key": "base", "label": "取り込み先"}, {"key": "url", "label": "URL"}],
            "labels": {"state": {"open": "提出中", "merged": "取り込み済み", "closed": "閉じた", "": "提出していません"},
                       "draft": {"true": "下書き", "false": "いいえ"},
                       "partial": {"true": "タスクを続ける（中間提出）", "false": "タスクを完了する"}},
        }},
        {"id": "activity", "part": "facts", "props": {
            "items": [{"key": "mergeable", "label": "取り込めるか"}],
            "labels": {"mergeable": {"MERGEABLE": "取り込めます", "UNKNOWN": "確認中",
                                     "CONFLICTING": "衝突があります（タスクブランチで最新を取り込んで直します）"}},
        }},
        # 提出に付いた CI の結果・レビュー・コメント
        {"id": "checks", "part": "table", "props": {
            "columns": [{"key": "name", "label": "CI"}, {"key": "status", "label": "状態"}, {"key": "conclusion", "label": "結果"}],
            "key": "name", "empty_text": "CI の結果はありません。",
            "labels": {"status": {"completed": "終わった", "in_progress": "実行中", "queued": "待っている"},
                       "conclusion": {"success": "成功", "failure": "失敗", "cancelled": "取り消し", "skipped": "飛ばした"}},
        }},
        {"id": "reviews", "part": "table", "props": {
            "columns": [{"key": "author", "label": "レビューした人"}, {"key": "state", "label": "判定"}, {"key": "body", "label": "コメント"}],
            "key": "author", "empty_text": "レビューはまだありません。",
            "labels": {"state": {"APPROVED": "承認", "CHANGES_REQUESTED": "差し戻し", "COMMENTED": "コメント"}},
        }},
        {"id": "comments", "part": "table", "props": {
            "columns": [{"key": "author", "label": "だれが"}, {"key": "body", "label": "提出へのコメント"}],
            "key": "author", "empty_text": "提出へのコメントはまだありません。",
        }},
        {"id": "diff", "part": "text-view", "props": {"empty_text": "差分はありません。"}},
        # コメント：タスクへのコメントにも、承認・差し戻しに添える文にも使う
        {"id": "talk", "layout": "row", "children": ["message", "do_comment"]},
        {"id": "message", "part": "text-input", "props": {"title": "コメント（差し戻すときは、直してほしいこと）", "placeholder": "承認に添えるのは任意"}},
        {"id": "do_comment", "part": "button", "props": {"label": "タスクにコメント", "hint": "作業の記録・申し送りを、タスクに残す"}},
        {"id": "judge_title", "part": "note", "props": {"text": "ほかの人の提出を見る"}},
        {"id": "judge", "layout": "row", "children": ["review", "review_done", "reject", "approve"]},
        {"id": "review", "part": "button", "props": {"label": "手元で確認", "hint": "確認用の作業空間に取り出す（ビルド・試験ができる）"}},
        {"id": "review_done", "part": "button", "props": {"label": "判定せずに終える", "hint": "確認用の作業空間を消す"}},
        {"id": "reject", "part": "button", "props": {"label": "差し戻す", "hint": "タスクは作業中に戻る（直してほしいことを、コメントの欄に書く）"}},
        {"id": "approve", "part": "button", "props": {"label": "承認して取り込む", "primary": True, "hint": "CI が終わるのを待って取り込む"}},
        {"id": "own_title", "part": "note", "props": {"text": "自分の提出"}},
        {"id": "own", "layout": "row", "children": ["withdraw", "finish", "apply"]},
        {"id": "withdraw", "part": "button", "props": {"label": "提出を取り下げる", "hint": "作業中に戻す（タスクブランチはそのまま）"}},
        {"id": "finish", "part": "button", "props": {"label": "取り込む", "hint": "提出を取り込み、提出のとおりタスクを完了するか続ける"}},
        {"id": "apply", "part": "button", "props": {"label": "反映", "hint": "提出を使わずに、作成元へ直接入れて完了する（作成元を管理している人）"}},
        # 取り込みのオプション（取り込む・承認して取り込む・反映に付く。選ばなければ既定のまま）
        {"id": "options_title", "part": "note", "props": {"text": "取り込みのオプション（選ばなければ、提出のとおり）"}},
        {"id": "options", "layout": "row", "children": ["subject", "ignore_checks", "partial", "complete"]},
        {"id": "subject", "part": "text-input", "props": {"title": "取り込むコミットの件名", "placeholder": "空なら、タスクの題名"}},
        {"id": "ignore_checks", "part": "toggle", "props": {"label": "CI が失敗していても取り込む", "hint": "CI を待たない（取り込む・承認して取り込む）"}},
        {"id": "partial", "part": "toggle", "props": {"label": "タスクを続ける（中間の取り込み）", "hint": "取り込んでもタスクを閉じない（取り込む・反映）"}},
        {"id": "complete", "part": "toggle", "props": {"label": "タスクを完了する", "hint": "中間提出でも、取り込んでタスクを閉じる（取り込む）"}},
    ],
    "bindings": [
        # 読む：task status は1回だけ実行され、いくつもの部品と、出し分けに使う共有の値へ出る
        {"read": "task status", "args": {"module": {"arg": "module"}, "issue": {"arg": "task"}}, "to": "info.data"},
        # 提出（pull_request）とその様子（activity）は、提出していなければ null。共有の値を通して出す（null なら、部品は空に戻る）
        {"read": "task status", "args": {"module": {"arg": "module"}, "issue": {"arg": "task"}}, "into": "pull_request", "from": "pull_request"},
        {"read": "task status", "args": {"module": {"arg": "module"}, "issue": {"arg": "task"}}, "into": "activity", "from": "activity"},
        {"value": "pull_request", "to": "pull_request.data"},
        {"value": "activity", "to": "activity.data"},
        {"value": "activity", "to": "checks.rows", "from": "checks"},
        {"value": "activity", "to": "reviews.rows", "from": "reviews"},
        {"value": "activity", "to": "comments.rows", "from": "comments"},
        {"read": "task status", "args": {"module": {"arg": "module"}, "issue": {"arg": "task"}}, "into": "own_task", "from": "task_branch"},
        {"read": "task status", "args": {"module": {"arg": "module"}, "issue": {"arg": "task"}}, "into": "submission_state", "from": "pull_request.state"},
        {"read": "task diff", "args": {"module": {"arg": "module"}, "task": {"arg": "task"}}, "to": "diff.text"},
        {"on": "reload.pressed", "refresh": True},
        # 出し分け。手元にタスクブランチがない（ほかの人の提出）：確認・差し戻し・承認。ある（自分の作業）：取り下げ・取り込み・反映。
        # 取り下げ・取り込み・判定は、提出が開いているときだけ（反映は、提出を使わない）
        {"show": "judge_title", "when": {"own_task": False, "submission_state": "open"}},
        {"show": "review", "when": {"own_task": False, "submission_state": "open"}},
        {"show": "review_done", "when": {"own_task": False, "submission_state": "open"}},
        {"show": "reject", "when": {"own_task": False, "submission_state": "open"}},
        {"show": "approve", "when": {"own_task": False, "submission_state": "open"}},
        {"show": "own_title", "when": {"own_task": True}},
        {"show": "withdraw", "when": {"own_task": True, "submission_state": "open"}},
        {"show": "finish", "when": {"own_task": True, "submission_state": "open"}},
        {"show": "apply", "when": {"own_task": True}},
        {"show": "complete", "when": {"own_task": True}},
        # 入力欄は共有の値に結ぶ：実行の後に共有の値を空にすると、欄も空に戻る
        {"on": "message.changed", "set": {"message": {"payload": "text"}}},
        {"value": "message", "to": "message.text"},
        {"on": "subject.changed", "set": {"subject": {"payload": "text"}}},
        {"value": "subject", "to": "subject.text"},
        {"on": "ignore_checks.changed", "set": {"ignore_checks": {"payload": "on"}}},
        {"value": "ignore_checks", "to": "ignore_checks.on"},
        {"on": "partial.changed", "set": {"partial": {"payload": "on"}}},
        {"value": "partial", "to": "partial.on"},
        {"on": "complete.changed", "set": {"complete": {"payload": "on"}}},
        {"value": "complete", "to": "complete.on"},
        # タスクにコメント（ecobuild task comment --issue <番号> --message <文>）。文を書くまで押せない
        {"on": "do_comment.pressed", "run": "task comment", "require": ["message"],
         "args": {"module": {"arg": "module"}, "issue": {"arg": "task"}, "message": {"value": "message"}}, "set": {"message": None}},
        # ほかの人の提出（ecobuild task review --task <番号> [--done]・task approve <番号> [--message <文>] [--subject <件名>]
        # [--ignore-checks]・task reject <番号> --message <文>）。差し戻しは、直してほしいことを書くまで押せない
        {"on": "review.pressed", "run": "task review", "args": {"module": {"arg": "module"}, "task": {"arg": "task"}}},
        {"on": "review_done.pressed", "run": "task review", "args": {"module": {"arg": "module"}, "task": {"arg": "task"}, "done": True}},
        {"on": "approve.pressed", "run": "task approve",
         "args": {"module": {"arg": "module"}, "task": {"arg": "task"}, "message": {"value": "message"}, "subject": {"value": "subject"},
                  "ignore_checks": {"value": "ignore_checks"}},
         "set": {"message": None, "subject": None, "ignore_checks": None}},
        {"on": "reject.pressed", "run": "task reject", "require": ["message"],
         "args": {"module": {"arg": "module"}, "task": {"arg": "task"}, "message": {"value": "message"}}, "set": {"message": None}},
        # 自分の提出（ecobuild task withdraw --task <番号>・task finish --task <番号> [--subject <件名>] [--ignore-checks] [--partial]
        # [--complete]・task apply --task <番号> [--subject <件名>] [--partial]）
        {"on": "withdraw.pressed", "run": "task withdraw", "args": {"module": {"arg": "module"}, "task": {"arg": "task"}}},
        {"on": "finish.pressed", "run": "task finish",
         "args": {"module": {"arg": "module"}, "task": {"arg": "task"}, "subject": {"value": "subject"},
                  "ignore_checks": {"value": "ignore_checks"}, "partial": {"value": "partial"}, "complete": {"value": "complete"}},
         "set": {"subject": None, "ignore_checks": None, "partial": None, "complete": None}},
        {"on": "apply.pressed", "run": "task apply",
         "args": {"module": {"arg": "module"}, "task": {"arg": "task"}, "subject": {"value": "subject"}, "partial": {"value": "partial"}},
         "set": {"subject": None, "partial": None}},
    ],
}
