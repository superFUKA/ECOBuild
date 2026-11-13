"""入力の窓：ほかの人の提出が作成元と衝突して、承認・取り込み（task approve）が止まった（何も変えていない）とき。

承認の入力の窓が、衝突で失敗したときに、その窓をこれに切り替える（つなぎの instead）。
タスクブランチの作業者に、最新を取り込んで直してもらう（差し戻す：ecobuild task reject <番号> --message …）。
"""

ARGS = {"module": ".", "issue": 0}  # モジュールのフォルダー・タスクの番号

SCREEN = {
    "root": "page",
    "window": {"title": "衝突しています", "width": 560, "height": 460},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "取り込めません：#{issue}", "ok": "差し戻す", "danger": True, "vars": {"issue": {"arg": "issue"}},
            "intro": "作成元（{base}）と衝突しているので、止めました（何も変えていません）。",
            "detail": "タスクブランチの作業者に、最新を取り込んで直してもらいます（差し戻し）。タスクは作業中に戻ります。",
            "initial": {"message": "作成元と衝突しているので、タスクブランチへ作成元の最新を取り込んで直してください。"},
            "fields": [
                {"name": "message", "label": "直してほしいこと", "type": "textarea", "rows": 4, "required": True},
            ]}},
    ],
    "bindings": [
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}}, "to": "form.also"},
        {"on": "form.submitted", "run": "task reject", "confirmed": True, "notify": "差し戻しました。", "close": True, "require": ["message"],
         "args": {"module": {"arg": "module"}, "task": {"arg": "issue"}, "message": {"payload": "values.message"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
