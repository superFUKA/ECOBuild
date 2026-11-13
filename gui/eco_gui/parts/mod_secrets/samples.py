SAMPLES = [
    {"name": "ふつう", "props": {"names": ["ECOBUILD_DEPS_TOKEN", "SIGNING_KEY"]}},
    {"name": "管理者でない（削除は灰色）", "props": {"names": ["ECOBUILD_DEPS_TOKEN"], "admin": False}},
    {"name": "空", "props": {"names": []}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "権限がありません"}},
]
