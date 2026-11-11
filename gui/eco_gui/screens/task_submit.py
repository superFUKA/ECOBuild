"""入力の窓：このタスクブランチを提出する（ecobuild task submit [--title …] [--draft] [--reviewer …] --complete か --partial [--no-check]）。

作業空間の窓の中に重ねて開く（module は、その作業空間）。上に、作成元と衝突するファイルの赤い警告（GitHub の最新と比べる：
ecobuild status --fetch の base_conflicts）と「何が起きるか」の表。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": "."}  # タスクブランチの作業空間

SCREEN = {
    "root": "page",
    "window": {"title": "提出", "width": 600, "height": 640},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "提出：#{task}", "ok": "提出",
            "outcome": [
                {"label": "PR", "text": "出している提出に、Push したコミットが加わります", "show_if": {"pull_request.state": "open"}},
                {"label": "PR", "text": "作成元（{base}）へ出します（Push してから）", "hide_if": {"pull_request.state": "open"}},
                {"label": "取り込み", "text": "見る人の承認で取り込まれます"},
                {"label": "取り込まれたら", "text": "閉じて、タスクブランチを片付けます", "show_if": {"complete": True}},
                {"label": "取り込まれたら", "text": "閉じずに続けます（タスクブランチを作成元の最新から作り直します）", "show_if": {"complete": False}},
            ],
            "fields": [
                {"type": "note", "tone": "bad", "list_from": "base_conflicts",
                 "label": "{base} と衝突するファイルがあります。このままでは取り込めません。先に「最新を取り込む」で直してから提出すると確実です。"},
                {"name": "complete", "label": "取り込まれたらタスクを完了する", "type": "checkbox", "value_from": "pull_request.partial", "off_value": True,
                 "inverse": "partial"},
                {"name": "title", "label": "題名", "placeholder": "空欄ならタスクの題名"},
                {"name": "draft", "label": "下書きとして提出する", "type": "checkbox", "value_from": "pull_request.draft"},
                {"name": "reviewer", "label": "見てもらう人（カンマ区切り、任意）"},
                {"name": "check", "label": "提出の前・後のパイプラインを走らせる（モジュール › パイプラインで当てたもの。なければ何もしません）",
                 "type": "checkbox", "value": True},
            ]}},
    ],
    "bindings": [
        # GitHub の最新を見てから（衝突の警告は、今の作成元との比べ）
        {"read": "status", "args": {"module": {"arg": "module"}, "fetch": True}, "to": "form.values"},
        {"on": "form.submitted", "run": "task submit", "notify": "提出しました。", "close": True,
         "args": {"module": {"arg": "module"}, "title": {"payload": "values.title"}, "draft": {"payload": "values.draft"},
                  "reviewer": {"payload": "values.reviewer"}, "partial": {"payload": "values.partial"}, "complete": {"payload": "values.complete"},
                  "check": {"payload": "values.check"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
