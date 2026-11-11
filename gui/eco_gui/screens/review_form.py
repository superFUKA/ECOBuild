"""提出まわりの入力の窓：取り込む・完了にする・承認して取り込む・差し戻す・反映・コメント・提出・ブランチの提出の取り込み。

ほかの画面のボタンから、窓の中に重ねて開く（inside）。kind で、どの入力の窓かを選ぶ。上に「何が起きるか」の表が出る。
実行がうまくいったら閉じる。確認の要るコマンド（取り込み・承認・差し戻し等）は、本体が確認を出す。

開き方の例：{"on": …, "open": "review-form", "inside": True, "args": {"module": …, "kind": "finish", "id": <番号>, "base": <作成元>, "partial": <中間提出か>}}
"""

ARGS = {"module": ".", "kind": "finish", "id": "", "base": "", "partial": False, "submitted": False}

SCREEN = {
    "root": "page",
    "window": {"title": "提出", "width": 560, "height": 520},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "review-form", "props": {
            "kind": {"arg": "kind"}, "id": {"arg": "id"}, "base": {"arg": "base"}, "partial": {"arg": "partial"}, "submitted": {"arg": "submitted"}}},
    ],
    "bindings": [
        {"on": "form.cancelled", "close": True},
        # 取り込む（ecobuild task finish --task <番号> [--subject <件名>] [--ignore-checks] --complete|--partial）
        {"on": "form.submitted", "when": {"kind": "finish"}, "run": "task finish",
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}, "subject": {"payload": "subject"},
                  "ignore_checks": {"payload": "ignore_checks"}, "partial": {"payload": "partial"}, "complete": {"payload": "complete"}},
         "notify": "提出を取り込みました。", "close": True},
        # 完了にする（ecobuild task finish --task <番号> --complete [--ignore-checks]）
        {"on": "form.submitted", "when": {"kind": "complete"}, "run": "task finish",
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}, "ignore_checks": {"payload": "ignore_checks"}, "complete": True},
         "notify": "タスクを完了しました。", "close": True},
        # 承認して取り込む（ecobuild task approve <番号> [--message <文>] [--subject <件名>] [--ignore-checks]）
        {"on": "form.submitted", "when": {"kind": "approve"}, "run": "task approve",
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}, "message": {"payload": "message"}, "subject": {"payload": "subject"},
                  "ignore_checks": {"payload": "ignore_checks"}},
         "notify": "承認して取り込みました。", "close": True},
        # 差し戻す（ecobuild task reject <番号> --message <文>）
        {"on": "form.submitted", "when": {"kind": "reject"}, "run": "task reject",
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}, "message": {"payload": "message"}},
         "notify": "差し戻しました。", "close": True},
        # コメント（ecobuild task comment --issue <番号> --message <文>）
        {"on": "form.submitted", "when": {"kind": "comment"}, "run": "task comment",
         "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}, "message": {"payload": "message"}},
         "notify": "コメントしました。", "close": True},
        # 反映（ecobuild task apply --task <番号> [--subject <件名>] [--partial]）
        {"on": "form.submitted", "when": {"kind": "apply"}, "run": "task apply",
         "args": {"module": {"arg": "module"}, "task": {"payload": "id"}, "subject": {"payload": "subject"}, "partial": {"payload": "partial"}},
         "notify": "反映しました。", "close": True},
        # 提出（ecobuild task submit [--title <題名>] [--draft] [--reviewer <人>] --complete|--partial。その作業空間で）
        {"on": "form.submitted", "when": {"kind": "submit"}, "run": "task submit",
         "args": {"module": {"arg": "module"}, "title": {"payload": "title"}, "draft": {"payload": "draft"}, "reviewer": {"payload": "reviewer"},
                  "partial": {"payload": "partial"}, "complete": {"payload": "complete"}},
         "notify": "提出しました。", "close": True},
        # ブランチ同士の提出を取り込む（ecobuild branch merge <ブランチ> [--ignore-checks]）
        {"on": "form.submitted", "when": {"kind": "merge"}, "run": "branch merge",
         "args": {"module": {"arg": "module"}, "name": {"payload": "id"}, "ignore_checks": {"payload": "ignore_checks"}},
         "notify": "ブランチの提出を取り込みました。", "close": True},
    ],
}
