SAMPLES = [
    {"name": "ふつう", "props": {"items": [{"key": "name", "label": "名前"}, {"key": "private", "label": "公開"}],
                              "data": {"name": "Calc", "private": True}, "labels": {"private": {"true": "非公開", "false": "公開"}}}},
    {"name": "色の印", "props": {"items": [{"key": "name", "label": "名前"}, {"key": "private", "label": "公開"}],
                               "data": {"name": "Calc", "private": True}, "labels": {"private": {"true": "非公開", "false": "公開"}},
                               "tones": {"private": {"true": "plain", "false": "ok"}}}},
    {"name": "読み込み中", "props": {"items": [{"key": "name", "label": "名前"}], "loading": True}},
    {"name": "誤り", "props": {"items": [{"key": "name", "label": "名前"}], "error": "モジュールではありません"}},
]
