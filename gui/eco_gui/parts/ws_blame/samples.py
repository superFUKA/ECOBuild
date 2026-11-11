SAMPLES = [
    {"name": "コミットごとの帯・続く行はまとめる", "props": {"text": (
        "^a215f21 (superFUKA 2026-10-05  1) [build-system]\n"
        "^a215f21 (superFUKA 2026-10-05  2) requires = [\"setuptools>=68\"]\n"
        "^a215f21 (superFUKA 2026-10-05  3) build-backend = \"setuptools.build_meta\"\n"
        "^a215f21 (superFUKA 2026-10-05  4) \n"
        "86115dbb (octocat   2026-10-13  5) [project]\n"
        "86115dbb (octocat   2026-10-13  6) name = \"calc\"\n"
        "3faa9ab3 (hubot     2026-11-01  7) version = \"0.2.0\"\n"
        "86115dbb (octocat   2026-10-13  8) description = \"長い行は、折り返さずに横へスクロールする。長い行は、折り返さずに横へスクロールする。長い行は、折り返さずに横へスクロールする。\"\n")}},
    {"name": "コミットを選んでいる", "props": {"selected": "86115dbb", "text": (
        "^a215f21 (superFUKA 2026-10-05  1) def add(a, b):\n"
        "86115dbb (octocat   2026-10-13  2)     \"\"\"足す。\"\"\"\n"
        "86115dbb (octocat   2026-10-13  3)     return a + b\n"
        "^a215f21 (superFUKA 2026-10-05  4) \n")}},
    {"name": "まだコミットしていない", "props": {"text": ""}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "README.md は、まだ git の管理に入っていないファイルです。"}},
]
