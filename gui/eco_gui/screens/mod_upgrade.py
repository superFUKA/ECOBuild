"""入力の窓：モジュールを最新の仕様にする（ecobuild module upgrade [--branch <ブランチ>]）。

実行する前に、下見（ecobuild module upgrade --dry-run）で、変えるファイルの一覧と仕様の版（今 → 最新）を見せる。
ブランチの詳細・設定・作業空間の帯から、窓の中に重ねて開く。うまくいったら閉じる（Esc・キャンセルでも閉じる）。
"""

ARGS = {"module": ".", "branch": ""}  # モジュールのフォルダー（作業空間）・合わせるブランチ（空なら、その場所で今いるブランチ）

SCREEN = {
    "root": "page",
    "window": {"title": "最新の仕様にする", "width": 600, "height": 560},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "最新の仕様にする", "subject": {"arg": "branch"}, "ok": "最新の仕様にする", "vars": {"branch": {"arg": "branch"}},
            "fields": [
                {"type": "note", "hide_if": {"branch": ""},
                 "label": "GitHub の {branch} を、今の ECOBuild の仕様に合わせます（生成ファイルも作り直します）。"
                          "変えたファイルは「ECOBuild の更新」として {branch} にコミットし、GitHub へ push します。手元の作業ツリーには触れません。"},
                {"type": "note", "show_if": {"branch": ""},
                 "label": "今いるブランチを、今の ECOBuild の仕様に合わせます（生成ファイルも作り直します）。"
                          "変えたファイルは「ECOBuild の更新」としてコミットします（タスクブランチなら、Push・提出はいつものとおり。ほかは GitHub へ push も）。"},
                {"type": "note", "list_from": "paths", "label": "変えるファイル（仕様の版 {format} → {latest_format}）：",
                 "empty_text": "変えるファイルはありません（今の仕様です）。"},
                {"type": "note", "list_from": "skipped", "label": "手で編集してあるため、作り直さないファイル："},
            ]}},
    ],
    "bindings": [
        # 下見：何も変えずに、変えるファイルを答える
        {"read": "module upgrade", "preview": True, "args": {"module": {"arg": "module"}, "branch": {"arg": "branch"}}, "to": "form.values"},
        {"on": "form.submitted", "run": "module upgrade", "args": {"module": {"arg": "module"}, "branch": {"arg": "branch"}},
         "notify": "最新の仕様にしました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
