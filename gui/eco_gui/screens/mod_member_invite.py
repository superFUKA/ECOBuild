"""モジュール › メンバー › 招待：入力の窓。GitHub のユーザー名と役割を決めて、共同作業者に招待する。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "メンバーを招待", "width": 560, "height": 420},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "メンバーを招待", "ok": "招待",
            "intro": "GitHub のアカウントを共同作業者に招待します。相手が GitHub の通知・メールから受けると加わり、タスク管理の情報も共有されます。",
            "fields": [
                {"name": "user", "label": "GitHub のユーザー名", "type": "text", "required": True, "placeholder": "例：octocat"},
                {"name": "role", "label": "役割", "type": "select", "none_label": "既定（書き込み）",
                 "help": "役割を選べるのは、組織のリポジトリだけです（個人のアカウントのリポジトリでは「書き込み」だけ）。",
                 "options": [{"value": "read", "label": "読む（read）"}, {"value": "triage", "label": "タスクの整理（triage）"},
                             {"value": "write", "label": "書き込み（write）"}, {"value": "maintain", "label": "管理の一部（maintain）"},
                             {"value": "admin", "label": "管理者（admin）"}]},
            ]}},
    ],
    "bindings": [
        # 人が打つのと同じ：ecobuild module members add <user> [--role <role>]
        {"on": "form.submitted", "run": "module members add", "confirmed": True,
         "args": {"module": {"arg": "module"}, "user": {"payload": "values.user"}, "role": {"payload": "values.role"}},
         "notify": "招待しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
