SAMPLES = [
    {"name": "ブランチを作成", "props": {
        "title": "ブランチを作成", "ok": "作成", "initial": {"base": "develop"},
        "fields": [
            {"name": "name", "label": "ブランチ名（task/ で始まる名前はタスクブランチ専用）", "type": "text", "required": True, "placeholder": "例：develop"},
            {"name": "base", "label": "作成元", "type": "select", "source": "rows", "where": {"is_task_branch": False}, "none_label": "既定（default_base）"},
        ],
        "rows": [{"name": "main", "is_task_branch": False}, {"name": "develop", "is_task_branch": False}, {"name": "task/12-login", "is_task_branch": True}],
    }},
    {"name": "チェックと切り替え", "props": {
        "title": "CIを用意する", "intro": "ワークフローを、この設定で作り直します。", "ok": "作る",
        "initial": {"os": "linux", "configuration": "Debug", "shared": "off"},
        "fields": [
            {"name": "os", "label": "動かすOS", "type": "checks", "join": ",",
             "options": [{"value": "windows", "label": "Windows"}, {"value": "linux", "label": "Linux"}]},
            {"name": "configuration", "label": "ビルドする構成（カンマ区切り）", "type": "text", "required": True, "hint": "例：Debug,Release"},
            {"name": "shared", "label": "共有ライブラリにした構成でもビルド・テストする", "type": "toggle", "on": "on", "off": "off"},
            {"type": "note", "label": "コミットして提出すると反映されます。"},
        ],
    }},
    {"name": "戻せない操作", "props": {"title": "CIをやめる", "ok": "消す", "danger": True, "fields": [
        {"name": "place", "label": "タスクブランチ（作業空間）", "type": "select", "source": "rows", "value_key": "path", "label_key": "branch", "note_key": "path"}],
        "rows": [{"path": "C:/work/Calc/.ecobuild/w/12", "branch": "task/12-login"}]}},
    {"name": "読み込み中", "props": {"title": "選ぶ", "loading": True, "fields": [{"name": "branch", "label": "ブランチ", "type": "select", "source": "rows"}]}},
    {"name": "誤り", "props": {"title": "選ぶ", "error": "一覧を読めません", "fields": [{"name": "branch", "label": "ブランチ", "type": "select", "source": "rows"}]}},
]
