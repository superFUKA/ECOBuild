"""入力の窓：閉じたタスクを開き直して、計画中か未着手にする（ecobuild task reopen <番号> --stage planned か todo）。

ボードで、完了・削除済みのタスクを計画中・未着手の列へ落としたときに、中に重ねて開く（落とした列は、窓へ渡す文字 text）。
うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "issue": 0, "text": "todo"}  # モジュールのフォルダー・タスクの番号・開き直した後の段階（planned・todo）

SCREEN = {
    "root": "page",
    "window": {"title": "開き直す", "width": 520, "height": 280},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "#{issue} を開き直す", "ok": "開き直す", "vars": {"issue": {"arg": "issue"}, "stage": {"arg": "text"}},
            "fields": [
                {"type": "note", "label": "「{title}」を開き直して、計画中にします。", "show_if": {"stage": "planned"}},
                {"type": "note", "label": "「{title}」を開き直して、未着手にします。", "hide_if": {"stage": "planned"}},
            ]}},
    ],
    "bindings": [
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}}, "to": "form.values"},
        {"on": "form.submitted", "run": "task reopen", "notify": "開き直しました。", "close": True,
         "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}, "stage": {"arg": "text"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
