"""モジュール › パイプライン › 削除：入力の窓。消すタスクブランチ（作業空間）を選び、外れるタイミングを確かめて、消す。"""

ARGS = {"module": ".", "name": "", "used": ""}  # モジュールのフォルダー・消すパイプライン・当てているタイミング（説明に出す）

SCREEN = {
    "root": "page",
    "window": {"title": "パイプラインを削除", "width": 560, "height": 360},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "パイプラインを削除", "subject": {"arg": "name"}, "ok": "削除する", "danger": True,
            "intro": "このパイプラインを消します。当てているタイミングからも外れます。", "detail": {"arg": "used"},
            "fields": [
                {"name": "place", "label": "消すタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "rows", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.rows", "from": "workspaces"},
        # 人が打つのと同じ：（作業空間で）ecobuild pipeline remove <名前>
        {"on": "form.submitted", "run": "pipeline remove", "args": {"module": {"payload": "values.place"}, "name": {"arg": "name"}},
         "require": ["module"], "notify": "パイプラインを消しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
