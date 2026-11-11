"""モジュール › メンバー › 役割：入力の窓。共同作業者の役割を変える（組織のリポジトリ）。"""

ARGS = {"module": ".", "user": "", "role": "write"}  # モジュールのフォルダー・相手のアカウント・今の役割

SCREEN = {
    "root": "page",
    "window": {"title": "役割", "width": 520, "height": 320},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "mod-form", "props": {
            "title": "役割を変える", "subject": {"arg": "user"}, "ok": "変える", "initial": {"role": {"arg": "role"}},
            "fields": [
                {"name": "role", "label": "役割", "type": "select",
                 "options": [{"value": "read", "label": "読む（read）"}, {"value": "triage", "label": "タスクの整理（triage）"},
                             {"value": "write", "label": "書き込み（write）"}, {"value": "maintain", "label": "管理の一部（maintain）"},
                             {"value": "admin", "label": "管理者（admin）"}]},
            ]}},
    ],
    "bindings": [
        # 人が打つのと同じ：ecobuild module members add <user> --role <role>（もういる人には、役割を変える）
        {"on": "form.submitted", "run": "module members add",
         "args": {"module": {"arg": "module"}, "user": {"arg": "user"}, "role": {"payload": "values.role"}},
         "notify": "役割を変えました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
