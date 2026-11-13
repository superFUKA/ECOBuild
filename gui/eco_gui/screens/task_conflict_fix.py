"""入力の窓：自分の提出が作成元と衝突して、取り込み（task finish）・反映（task apply）が止まった（何も変えていない）とき。

取り込み・完了・反映の入力の窓が、衝突で失敗したときに、その窓をこれに切り替える（つなぎの instead）。
「取り込んで直す」で、タスクブランチの作業空間を開く（手元になければ GitHub から取り出す：ecobuild task start <番号>）。
そこで作成元の最新を取り込み（取り込む）、衝突を直して Push してから、もう一度取り込む。
"""

ARGS = {"module": ".", "issue": 0, "title": "取り込めません", "files": []}
# モジュールのフォルダー・タスクの番号・題（反映なら「反映できません」）・衝突するファイル（誤りの details）

SCREEN = {
    "root": "page",
    "window": {"title": "衝突しています", "width": 560, "height": 380},
    "nodes": [
        {"id": "page", "layout": "column", "look": "tk-dialog", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "{title}：#{issue}", "ok": "取り込んで直す", "vars": {"issue": {"arg": "issue"}, "title": {"arg": "title"}, "files": {"arg": "files"}},
            "intro": "作成元（{base}）と衝突しているので、止めました（何も変えていません）。",
            "detail": "タスクブランチへ {base} の最新を取り込んで直します。作業空間を開くので、「取り込む」で最新を取り込み、"
                      "衝突したら直して「続ける」を押し、Push してから、もう一度取り込みます。",
            "fields": [
                {"type": "note", "tone": "warn", "label": "衝突するファイル：", "list_from": "files"},
            ]}},
    ],
    "bindings": [
        {"read": "task status", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}}, "to": "form.values"},
        {"on": "form.submitted", "run": "task start", "args": {"module": {"arg": "module"}, "issue": {"arg": "issue"}}, "close": True,
         "notify": "作業空間を開きました。{base} の最新を取り込み（取り込む）、衝突を直して Push してから、もう一度取り込んでください。",
         "after": {"open": "frame-workspace", "args": {"module": {"arg": "module"}, "space": {"result": "workspace"}}}},
        {"on": "form.cancelled", "close": True},
    ],
}
