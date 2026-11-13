"""入力の窓：タスクを削除する（ecobuild task close <番号> --not-planned）。タスクは、あとで「元に戻す」で戻せる。

タスクブランチ（手元か GitHub）があれば、その作業（タスクブランチと提出）はこのPCと GitHub から消え、戻せないことを赤い帯で出す
（GitHub の「危ない操作」と同じ）。タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号・窓へ渡す文字（使わない）

SCREEN = {
    "root": "page",
    "window": {"title": "削除", "width": 560, "height": 340},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "#{issue} を削除", "ok": "削除", "danger": True, "vars": {"issue": {"arg": "issue"}},
            "intro": "「{title}」を削除します。タスクは、あとで「元に戻す」で戻せます。",
            "fields": [
                {"type": "note", "tone": "bad", "label": "このタスクの作業（タスクブランチと提出）は、このPCとGitHubから消えます。作業は戻せません。",
                 "show_if": {"task_branch": True}},
                {"type": "note", "tone": "bad", "label": "このタスクの作業（タスクブランチと提出）は、このPCとGitHubから消えます。作業は戻せません。",
                 "show_if": {"task_branch": False, "remote": True}},
            ]}},
    ],
    "bindings": [
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}}, "to": "form.values"},
        {"on": "form.submitted", "run": "task close", "confirmed": True, "notify": "#{number} を削除しました。", "close": True,
         "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}, "not_planned": True}},
        {"on": "form.cancelled", "close": True},
    ],
}
