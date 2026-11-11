"""モジュール › パイプライン › 作る・変える：入力の窓。名前・手順（チェック）・流す試験を決める。

ecobuild.toml を変えるので、タスクブランチの作業空間で実行する（選んだ作業空間が、コマンドの実行先）。
"""

ARGS = {"module": ".", "name": "", "steps": "", "tests": ""}  # モジュールのフォルダーと、今の中身（変えるときの初めの値）

SCREEN = {
    "root": "page",
    "window": {"title": "パイプライン", "width": 620, "height": 620},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "mod-form", "props": {
            "title": "パイプラインを作る・変える", "ok": "決める",
            "intro": "選んだ手順を、上から順に行います。作っただけでは走りません（「▶ 実行」か、タイミングに当てて走らせます）。",
            "initial": {"name": {"arg": "name"}, "steps": {"arg": "steps"}, "tests": {"arg": "tests"}},
            "fields": [
                {"name": "place", "label": "変えるタスクブランチ（作業空間）", "type": "select", "source": "rows", "value_key": "path",
                 "label_key": "branch", "note_key": "path", "where": {"review": None}, "required": True,
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）"},
                {"name": "name", "label": "名前（例：quick、full。同じ名前があれば、その中身を変えます）", "type": "text", "required": True},
                {"name": "steps", "label": "手順", "type": "checks", "join": ",", "required": True, "options": [
                    {"value": "generated", "label": "生成ファイルが最新か"}, {"value": "conflict_markers", "label": "衝突の印（<<<<<<< 等）がないか"},
                    {"value": "build", "label": "ビルド"}, {"value": "test", "label": "テスト"}]},
                {"name": "tests", "label": "テストで流す試験（カンマ区切り。空なら全部。型が絞れるとき）", "type": "text",
                 "placeholder": "例：tests/unit,gui/tests"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.rows", "from": "workspaces"},
        # 人が打つのと同じ：（作業空間で）ecobuild pipeline add <名前> --steps <手順,…> [--tests <試験,…>]
        {"on": "form.submitted", "run": "pipeline add", "args": {
            "module": {"payload": "values.place"}, "name": {"payload": "values.name"}, "steps": {"payload": "values.steps"},
            "tests": {"payload": "values.tests"}},
         "require": ["module"], "notify": "パイプラインを決めました。コミットして提出すると共有されます。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
