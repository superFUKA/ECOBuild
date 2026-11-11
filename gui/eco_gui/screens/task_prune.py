"""入力の窓：このPCのタスクブランチだけを消す（ecobuild task prune <番号>）。

タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（使わない）

SCREEN = {
    "root": "page",
    "window": {"title": "このPCから片付ける", "width": 560, "height": 320},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "このPCから片付ける：#{issue}", "ok": "消す", "danger": True, "vars": {"issue": {"arg": "issue"}},
            "intro": "このPCのタスクブランチだけを消します。GitHubのブランチ・提出・タスクは残るので、「作業を再開」でPushしたところから続けられます。\n"
                     "未コミット・未Pushの変更があるときは消しません。",
            "fields": []}},
    ],
    "bindings": [
        {"on": "form.submitted", "run": "task prune", "notify": "このPCのタスクブランチを片付けました。", "close": True,
         "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
