"""モジュール › パイプライン › タイミングの当て方を変える：入力の窓。そのタイミングに走らせるパイプラインを選ぶ（モジュールで共有する当て方）。

ecobuild.toml を変えるので、タスクブランチの作業空間で実行する（選んだ作業空間が、コマンドの実行先）。
"""

ARGS = {"module": ".", "timing": "", "names": "", "label": ""}  # モジュールのフォルダー・タイミング・今の当て方（カンマ区切り）・呼び名

SCREEN = {
    "root": "page",
    "window": {"title": "走らせるパイプライン", "width": 600, "height": 520},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "mod-form", "props": {
            "title": "走らせるパイプライン", "subject": {"arg": "label"}, "ok": "決める",
            "intro": "選んだものを、並んでいる順に走らせます。「前」のタイミングは、どれかが失敗したら、その操作を止めます。"
                     "「後」は、失敗しても操作は止めず、知らせるだけです。1つも選ばなければ、何も走らせません。",
            "initial": {"names": {"arg": "names"}},
            "fields": [
                {"name": "place", "label": "変えるタスクブランチ（作業空間）", "type": "select", "source": "rows", "value_key": "path",
                 "label_key": "branch", "note_key": "path", "where": {"review": None}, "required": True,
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）"},
                {"name": "names", "label": "パイプライン", "type": "checks", "source": "more", "note_key": "steps", "join": ",", "empty": "none",
                 "empty_text": "パイプラインがありません。"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.rows", "from": "workspaces"},
        {"read": "pipeline list", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "pipelines"},
        # 人が打つのと同じ：（作業空間で）ecobuild pipeline on <タイミング> <名前,…|none>
        {"on": "form.submitted", "run": "pipeline on", "args": {
            "module": {"payload": "values.place"}, "timing": {"arg": "timing"}, "names": {"payload": "values.names"}},
         "require": ["module"], "notify": "当て方を変えました。コミットして提出すると共有されます。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
