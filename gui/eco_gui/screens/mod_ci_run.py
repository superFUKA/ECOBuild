"""モジュール › CI › 手動で実行：入力の窓。GitHub にあるブランチを選んで、CI を動かす。"""

ARGS = {"module": ".", "branch": ""}  # モジュールのフォルダー・初めに選んでおくブランチ（絞っていたブランチ）

SCREEN = {
    "root": "page",
    "window": {"title": "CIを手動で実行", "width": 560, "height": 320},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "CIを手動で実行", "ok": "実行", "initial": {"branch": {"arg": "branch"}},
            "intro": "GitHub にあるブランチの内容で CI を動かします（手元の未Pushのコミットは入りません）。",
            "fields": [
                {"name": "branch", "label": "ブランチ", "type": "select", "options_from": {"source": "rows", "where": {"remote": True}},
                 "none_label": "作成元のブランチ（既定）"},
            ]}},
    ],
    "bindings": [
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "form.rows"},
        # 人が打つのと同じ：ecobuild ci run [--branch <ブランチ>]
        {"on": "form.submitted", "run": "ci run", "args": {"module": {"arg": "module"}, "branch": {"payload": "values.branch"}},
         "notify": "CI を実行しました。少しすると一覧に出ます。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
