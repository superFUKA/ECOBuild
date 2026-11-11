"""入力の窓：衝突を直すタスクを作る（ecobuild branch resolve <ブランチ> --into <取り込み先>）。

ブランチ同士の取り込みのカードの中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "name": "", "into": ""}  # モジュールのフォルダー・取り込むブランチ・取り込み先

SCREEN = {
    "root": "page",
    "window": {"title": "衝突を直す", "width": 600, "height": 360},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "衝突を直す", "ok": "タスクを作る", "vars": {"name": {"arg": "name"}, "into": {"arg": "into"}},
            "intro": "{into} を {name} へ取り込むタスクを作り、作業空間に取り出して {into} を取り込みます（衝突したところで止まります）。",
            "detail": "作業空間で衝突したファイルを直して「続ける」、提出のタブで {name} へ入れる（このタスクはスカッシュせずに履歴ごと入ります）と、"
                      "{name} → {into} が取り込めるようになります。",
            "fields": []}},
    ],
    "bindings": [
        {"on": "form.submitted", "run": "branch resolve", "close": True,
         "notify": "衝突を直すタスク #{task} を作りました。作業空間で、衝突したファイルを直してください。",
         "args": {"module": {"arg": "module"}, "name": {"arg": "name"}, "into": {"arg": "into"}}},
        {"on": "form.cancelled", "close": True},
    ],
}
