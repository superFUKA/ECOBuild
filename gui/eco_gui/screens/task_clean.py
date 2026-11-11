"""入力の窓：閉じたタスクのタスクブランチと作業空間を、まとめて消す（ecobuild task prune）。

タスク管理の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": ""}  # モジュールのフォルダー・タスクの番号（使わない）・窓へ渡す文字（使わない）

SCREEN = {
    "root": "page",
    "window": {"title": "完了したタスクブランチを片付ける", "width": 560, "height": 300},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "完了したタスクブランチを片付ける", "ok": "片付ける",
            "intro": "閉じたタスクのタスクブランチと、その作業空間を消します。取り込んでいないコミットがあるものは残します（残したものと理由は、結果に出ます）。",
            "fields": []}},
    ],
    "bindings": [
        {"on": "form.submitted", "run": "task prune", "notify": "完了したタスクブランチを片付けました。", "close": True, "args": {"module": {"arg": "module"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
