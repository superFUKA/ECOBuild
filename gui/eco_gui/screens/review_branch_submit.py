"""入力の窓：ブランチを、別の共有ブランチへ提出する（ecobuild branch submit <ブランチ> --into <取り込み先> [--title <題名>]）。

ブランチの取り込み・提出の画面の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "name": "", "into": ""}  # モジュールのフォルダー・提出するブランチ・取り込み先の初めの値

SCREEN = {
    "root": "page",
    "window": {"title": "提出する", "width": 560, "height": 380},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "提出する", "subject": {"arg": "name"}, "ok": "提出", "initial": {"into": {"arg": "into"}},
            "intro": "取り込み先への提出（PR）を作ります。見てもらってから取り込みます。",
            "fields": [
                {"name": "into", "label": "取り込み先", "type": "select", "required": True, "none_label": "（選んでください）",
                 "options_from": {"source": "rows", "value": "name", "label": "name", "where": {"is_task_branch": False}}},
                {"name": "title", "label": "提出の題名", "type": "text", "placeholder": "空なら既定"},
            ]}},
    ],
    "bindings": [
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "form.rows"},
        {"on": "form.submitted", "run": "branch submit", "notify": "提出しました。", "close": True,
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "into": {"payload": "values.into"}, "title": {"payload": "values.title"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
