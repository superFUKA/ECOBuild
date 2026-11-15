"""モジュール › 依存先 › 作業版にする：入力の窓。依存先の手元の clone を、依存先のタスクブランチ（か、選んだブランチ）の
最新にする（ecobuild deps work <名前> [--task <番号>|--branch <ブランチ>]）。番号もブランチも空なら、今の作業版の取り直し。

記録（管理ファイル）は変えないので、作業空間を選ばない。表で見ている場所（モジュールのフォルダーか作業空間）の deps/ で行う。
"""

ARGS = {"module": ".", "name": "", "task": ""}  # モジュールのフォルダー・依存先・今の作業版のタスクの番号（あれば）

SCREEN = {
    "root": "page",
    "window": {"title": "作業版にする", "width": 600, "height": 440},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "依存先を作業版にする", "subject": {"arg": "name"}, "ok": "作業版にする",
            "initial": {"task": {"arg": "task"}},
            "intro": "依存先の手元の clone を、依存先のモジュールで作っている途中のタスク（push していないコミットも）にして、"
                     "このモジュールで build・test して試します。記録の版は変えません。提出の前の確かめ・CI は記録の版を使います。",
            "fields": [
                {"name": "task", "label": "依存先のタスクの番号", "type": "number", "min": 1,
                 "help": "依存先のリポジトリのタスク（Issue）の番号。このPCにそのタスクの作業空間があればそこから、なければ GitHub の"
                         "タスクブランチから取ります。番号もブランチも空なら、今の作業版を取り直します。"},
                {"name": "branch", "label": "ブランチ（番号の代わりに）",
                 "help": "タスクブランチでないブランチを使うとき。"},
            ]}},
    ],
    "bindings": [
        {"on": "form.submitted", "run": "deps work",
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "task": {"payload": "values.task"},
                  "branch": {"payload": "values.branch"}},
         "notify": "依存先を作業版にしました（記録の版は変えていません）。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
