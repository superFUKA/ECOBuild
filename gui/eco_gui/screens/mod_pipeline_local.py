"""モジュール › パイプライン › このPCで足す：入力の窓。そのタイミングに、この PC だけで足して走らせるパイプラインを選ぶ。

ecobuild.local.toml に書く（コミットしない）ので、どこでも使える。モジュールの当て方には上乗せするだけ。
"""

ARGS = {"module": ".", "timing": "", "names": "", "label": ""}  # モジュールのフォルダー・タイミング・今この PC で足しているもの・呼び名

SCREEN = {
    "root": "page",
    "window": {"title": "このPCで足すパイプライン", "width": 600, "height": 460},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "このPCで足すパイプライン", "subject": {"arg": "label"}, "ok": "決める",
            "intro": "モジュールの当て方に足すだけで、外せません。コミットせず、この PC のこの場所だけに効きます。"
                     "1つも選ばなければ、この PC で足したものをなくします。",
            "initial": {"names": {"arg": "names"}},
            "fields": [
                {"name": "names", "label": "パイプライン", "type": "checks", "options_from": {"source": "rows", "note": "steps"}, "join": ",", "empty": "none",
                 "empty_text": "パイプラインがありません。"},
            ]}},
    ],
    "bindings": [
        {"read": "pipeline list", "args": {"module": {"arg": "module"}}, "to": "form.rows", "from": "pipelines"},
        # 人が打つのと同じ：ecobuild pipeline on <タイミング> <名前,…|none> --local
        {"on": "form.submitted", "run": "pipeline on", "args": {
            "module": {"arg": "module"}, "timing": {"arg": "timing"}, "names": {"payload": "values.names"}, "local": True},
         "notify": "この PC だけで足しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
