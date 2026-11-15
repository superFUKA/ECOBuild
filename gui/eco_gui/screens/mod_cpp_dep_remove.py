"""モジュール › 依存先 › リンクを外す：入力の窓。依存先のリンクを外す（ecobuild deps remove <名前> [--library <ライブラリ>]）。

ライブラリを選ぶと、そのライブラリへのリンクだけを外す（記録と clone は残る。最後の1つなら依存先ごと外す）。選ぶものは
ecobuild deps libraries <名前> --linked（リンクしているものだけ）で読む。
"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・外す依存先

SCREEN = {
    "root": "page",
    "window": {"title": "リンクを外す", "width": 600, "height": 400},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "リンクを外す", "subject": {"arg": "name"}, "ok": "外す", "danger": True, "initial": {"place": {"arg": "module"}},
            "intro": "依存先のリンクを外します。手元のcloneは、記録の版のままなら削除します（作業中や変更がある場合は残します）。",
            "fields": [
                {"name": "library", "label": "外すもの", "type": "select", "none_label": "依存先ごと（すべてのリンクと記録）",
                 "options_from": {"source": "rows", "value": "name", "label": "name", "note": ["kind", "linked"],
                                  "note_labels": {
                     "static_library": "静的ライブラリ", "shared_library": "共有ライブラリ", "interface_library": "ヘッダーだけのライブラリ"}},
                 "help": "ライブラリを選ぶと、そのライブラリへのリンクだけを外します（かっこの中は、リンクしている Project）。記録と clone は残ります。"},
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        # リンクしているものだけ（依存先でなければ空。GitHub へは行かない）。表で見ている場所（表の行がある所）で読む
        {"read": "deps libraries", "args": {"module": {"arg": "module"}, "target": {"arg": "name"}, "linked": True}, "require": ["target"],
         "to": "form.rows", "from": "libraries"},
        {"on": "form.submitted", "run": "deps remove", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "name": {"arg": "name"}, "library": {"payload": "values.library"}},
         "notify": "リンクを外しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
