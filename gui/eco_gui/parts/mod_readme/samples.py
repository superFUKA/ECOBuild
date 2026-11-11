SAMPLES = [
    {"name": "Markdown", "props": {"readme": {"path": "README.md", "truncated": False, "text": (
        "# Calc\n\n足し算をする**小さな**ライブラリ。詳しくは [GitHub](https://github.com/octocat/Calc) を見てください。\n\n"
        "## 使い方\n\n1. `ecobuild build` でビルドする\n2. `ecobuild test` で確かめる\n\n"
        "- 速い\n- 小さい\n  続きの行\n\n> 注意：まだ試作です。\n\n```\nfrom calc import add\nprint(add(1, 2))\n```\n\n---\n\n### ライセンス\n\nMIT\n")}}},
    {"name": "文字だけ（長いので途中まで）", "props": {"readme": {"path": "README.txt", "text": "ただの文字の README です。\n2行目。", "truncated": True}}},
    {"name": "ない", "props": {"readme": None}},
    {"name": "読み込み中", "props": {"readme": None, "loading": True}},
    {"name": "誤り", "props": {"readme": None, "error": "モジュールではありません"}},
]
