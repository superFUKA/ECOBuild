"""提出：1つのタスクの提出。状態と差分を見て、確認・承認・差し戻し・取り下げ・取り込み・反映をする。"""

ARGS = {"module": ".", "task": ""}  # モジュールのフォルダー・タスクの番号（表の行の ID のまま、文字で受ける。コマンドへは数で渡る）

SCREEN = {
    "root": "page",
    "window": {"title": "提出", "width": 900, "height": 760},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "info", "pull_request", "activity", "diff", "message",
                                                        "judge_title", "judge", "own_title", "own"]},
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
            "labels": {"state": {"open": "提出中", "merged": "取り込み済み", "closed": "閉じた"},
                       "draft": {"true": "下書き", "false": "いいえ"},
                       "partial": {"true": "タスクを続ける（中間提出）", "false": "タスクを完了する"}},
        }},
        {"id": "activity", "part": "facts", "props": {
            "items": [{"key": "mergeable", "label": "取り込めるか"}],
            "labels": {"mergeable": {"MERGEABLE": "取り込めます", "UNKNOWN": "確認中",
                                     "CONFLICTING": "衝突があります（タスクブランチで最新を取り込んで直します）"}},
        }},
        {"id": "diff", "part": "text-view", "props": {"empty_text": "差分はありません。"}},
        {"id": "message", "part": "text-input", "props": {"title": "コメント（差し戻すときは、直してほしいこと）", "placeholder": "任意"}},
        {"id": "judge_title", "part": "note", "props": {"text": "ほかの人の提出を見る"}},
        {"id": "judge", "layout": "row", "children": ["review", "review_done", "reject", "approve"]},
        {"id": "review", "part": "button", "props": {"label": "手元で確認", "hint": "確認用の作業空間に取り出す（ビルド・試験ができる）"}},
        {"id": "review_done", "part": "button", "props": {"label": "判定せずに終える", "hint": "確認用の作業空間を消す"}},
        {"id": "reject", "part": "button", "props": {"label": "差し戻す", "hint": "タスクは作業中に戻る"}},
        {"id": "approve", "part": "button", "props": {"label": "承認して取り込む", "primary": True, "hint": "CI が終わるのを待って取り込む"}},
        {"id": "own_title", "part": "note", "props": {"text": "自分の提出"}},
        {"id": "own", "layout": "row", "children": ["withdraw", "finish", "apply"]},
        {"id": "withdraw", "part": "button", "props": {"label": "提出を取り下げる", "hint": "作業中に戻す（タスクブランチはそのまま）"}},
        {"id": "finish", "part": "button", "props": {"label": "取り込む", "hint": "提出を取り込み、提出のとおりタスクを完了するか続ける"}},
        {"id": "apply", "part": "button", "props": {"label": "反映", "hint": "提出を使わずに、作成元へ直接入れて完了する（作成元を管理している人）"}},
    ],
    "bindings": [
        # 読む：task status は1回だけ実行され、3つの部品へ出る
        {"read": "task status", "args": {"module": {"arg": "module"}, "issue": {"arg": "task"}}, "to": "info.data"},
        {"read": "task status", "args": {"module": {"arg": "module"}, "issue": {"arg": "task"}}, "to": "pull_request.data", "from": "pull_request"},
        {"read": "task status", "args": {"module": {"arg": "module"}, "issue": {"arg": "task"}}, "to": "activity.data", "from": "activity"},
        {"read": "task diff", "args": {"module": {"arg": "module"}, "task": {"arg": "task"}}, "to": "diff.text"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "message.changed", "set": {"message": {"payload": "text"}}},
        # ほかの人の提出（ecobuild task review --task <番号> [--done]・task approve <番号>・task reject <番号> --message <文>）
        {"on": "review.pressed", "run": "task review", "args": {"module": {"arg": "module"}, "task": {"arg": "task"}}},
        {"on": "review_done.pressed", "run": "task review", "args": {"module": {"arg": "module"}, "task": {"arg": "task"}, "done": True}},
        {"on": "approve.pressed", "run": "task approve",
         "args": {"module": {"arg": "module"}, "task": {"arg": "task"}, "message": {"value": "message"}}},
        {"on": "reject.pressed", "run": "task reject",
         "args": {"module": {"arg": "module"}, "task": {"arg": "task"}, "message": {"value": "message"}}},
        # 自分の提出（ecobuild task withdraw・task finish・task apply。どれも --task <番号>）
        {"on": "withdraw.pressed", "run": "task withdraw", "args": {"module": {"arg": "module"}, "task": {"arg": "task"}}},
        {"on": "finish.pressed", "run": "task finish", "args": {"module": {"arg": "module"}, "task": {"arg": "task"}}},
        {"on": "apply.pressed", "run": "task apply", "args": {"module": {"arg": "module"}, "task": {"arg": "task"}}},
    ],
}
