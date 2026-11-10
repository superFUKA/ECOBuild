SAMPLES = [
    {"name": "ふつう", "props": {
        "columns": [{"key": "configuration", "label": "構成"}, {"key": "shared", "label": "共有"}],
        "name_label": "ビルド設定", "current": "fast",
        "entries": {"fast": {"configuration": "Debug", "shared": False}, "ship": {"configuration": "Release", "shared": True}},
        "actions": [{"name": "use", "label": "使う"}, {"name": "remove", "label": "消す"}],
        "labels": {"shared": {"true": "共有ライブラリ", "false": ""}}}},
    {"name": "空", "props": {"columns": [{"key": "configuration", "label": "構成"}], "empty_text": "ビルド設定はありません。"}},
    {"name": "読み込み中", "props": {"columns": [{"key": "configuration", "label": "構成"}], "loading": True}},
    {"name": "誤り", "props": {"columns": [{"key": "configuration", "label": "構成"}], "error": "モジュールではありません"}},
]
