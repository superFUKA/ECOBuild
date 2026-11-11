"""タスクを描く部品を1つ置き、どの表示でも同じつなぎを付ける（一覧・ボード・日程・次にやる・スプリント・概要・右の詳細）。

選ぶと右の詳細に出す（共有の値 selected・detail）。入力の窓（開始・編集・完了・人の画面 ほか）は中に重ねて開く。
右クリックのメニュー・その場の欄・ドラッグでの変更は ecobuild task edit、完了・削除は task close、開き直すは task reopen。
"""

ARGS = {"module": ".", "part": "task-list", "look": "tk-main", "props": {}}
# モジュールのフォルダー・置く部品（出力 selected・dialog・edit・close・remove・reopen・workspace と、要る情報 sprints・me を持つもの）・
# 見た目の名前・部品に渡す要る情報

SCREEN = {
    "root": "view",
    "nodes": [
        {"id": "view", "part": {"arg": "part"}, "look": {"arg": "look"}, "props": {"arg": "props"}},
    ],
    "bindings": [
        {"read": "sprint list", "args": {"module": {"arg": "module"}}, "to": "view.sprints"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "view.me", "from": "login"},
        {"on": "view.selected", "set": {"selected": {"payload": "id"}, "detail": "open"}},
        {"on": "view.dialog", "open": {"payload": "screen"}, "inside": True,
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "text": {"payload": "text"}}},
        # その場で変える（ecobuild task edit <番号> --priority … ほか。入れた値だけが渡る）
        {"on": "view.edit", "run": "task edit", "notify": "保存しました。",
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"},
                  "priority": {"payload": "priority"}, "sprint": {"payload": "sprint"}, "stage": {"payload": "stage"}, "estimate": {"payload": "estimate"},
                  "due": {"payload": "due"}, "planned_start": {"payload": "planned_start"}, "planned_end": {"payload": "planned_end"},
                  "milestone": {"payload": "milestone"}, "clear_milestone": {"payload": "clear_milestone"},
                  "add_assignee": {"payload": "add_assignee"}, "remove_assignee": {"payload": "remove_assignee"},
                  "add_label": {"payload": "add_label"}, "remove_label": {"payload": "remove_label"}, "clear": {"payload": "clear"}}},
        {"on": "view.close", "run": "task close", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "notify": "完了にしました。"},
        {"on": "view.remove", "run": "task close", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "not_planned": True}, "notify": "削除しました。"},
        {"on": "view.reopen", "run": "task reopen", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "notify": "開き直しました。"},
        # タスクブランチを開く：同じ窓の「作業空間」のタブで出す
        {"on": "view.workspace", "open": "frame-workspace", "args": {"module": {"arg": "module"}, "space": {"payload": "path"}}, "here": True},
    ],
}
