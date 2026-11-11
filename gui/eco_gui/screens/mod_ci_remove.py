"""モジュール › CI › やめる：入力の窓。ワークフローを消すタスクブランチ（作業空間）を選ぶ。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "form",
    "window": {"title": "CIをやめる", "width": 560, "height": 320},
    "nodes": [
        {"id": "form", "part": "mod-form", "props": {
            "title": "CIをやめる", "ok": "消す", "danger": True,
            "intro": "ワークフロー（.github/workflows/ecobuild.yml）を消します。コミットして提出し、取り込むと反映されます。",
            "fields": [
                {"name": "place", "label": "タスクブランチ（作業空間）", "type": "select", "source": "rows", "value_key": "path",
                 "label_key": "branch", "note_key": "path", "where": {"review": None}, "required": True,
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.rows", "from": "workspaces"},
        # 人が打つのと同じ：（作業空間で）ecobuild ci remove
        {"on": "form.submitted", "run": "ci remove", "args": {"module": {"payload": "values.place"}}, "require": ["module"],
         "notify": "ワークフローを消しました。コミットして提出すると反映されます。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
