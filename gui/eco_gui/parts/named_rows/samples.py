SAMPLES = [
    {"name": "ふつう", "props": {
        "columns": [{"key": "configuration", "label": "構成"}, {"key": "parallel", "label": "並列の数"}],
        "data": {"debug": {"configuration": "Debug", "parallel": 4}, "release": {"configuration": "Release", "parallel": 8}},
        "name_label": "ビルド設定", "actions": [{"name": "use", "label": "使う"}, {"name": "remove", "label": "消す"}]}},
    {"name": "空", "props": {"columns": [{"key": "configuration", "label": "構成"}], "data": {}, "empty_text": "ビルド設定はまだありません。"}},
    {"name": "読み込み中", "props": {"columns": [{"key": "configuration", "label": "構成"}], "data": {}, "loading": True}},
    {"name": "誤り", "props": {"columns": [{"key": "configuration", "label": "構成"}], "data": {}, "error": "ecobuild.toml を読めません"}},
]
