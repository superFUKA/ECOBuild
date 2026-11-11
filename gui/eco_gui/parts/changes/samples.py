SAMPLES = [
    {"name": "ふつう", "props": {"status": {"staged": ["a.py"], "unstaged": ["b.py", "c.py"], "untracked": ["new.txt"]}, "checked": ["b.py"]}},
    {"name": "見出しの行・フォルダーの木・種類の色", "props": {
        "tools": True, "selected": "src/app.py", "missing": ["src/old.py"], "stashes": ["On task/12-login: 途中の変更"],
        "status": {"branch": "task/12-login", "staged": ["src/login.py", "src/app.py"], "unstaged": ["src/app.py", "src/old.py", "docs/guide/start/index.md", "README.md"],
                   "untracked": ["src/util/new.py", "notes.txt"], "conflicted": ["tests/test_app.py"], "eol_only": ["README.md"], "excluded": ["notes.txt"],
                   "merging": True},
        "checked": ["src/login.py", "src/app.py"]}},
    {"name": "サブプロジェクトごと（C++）", "props": {
        "tools": True,
        "projects": [{"name": "Calc", "kind": "static_library", "directory": "Calc"}, {"name": "CalcTest", "kind": "test", "directory": "CalcTest"}],
        "status": {"unstaged": ["Calc/src/Add.cpp", "Calc/include/Calc/Add.h", "CalcTest/src/AddTest.cpp", "ecobuild.toml"], "untracked": ["Calc/src/Sub.cpp"]},
        "checked": ["Calc/src/Add.cpp"]}},
    {"name": "生成ファイルの印", "props": {"generated": ["Calc/CMakeLists.txt"],
                              "status": {"staged": [], "unstaged": ["Calc/CMakeLists.txt", "Calc/src/Add.cpp"], "untracked": []}}},
    {"name": "変更なし", "props": {"status": {"staged": [], "unstaged": [], "untracked": []}}},
    {"name": "変更なし（見出しの行つき）", "props": {"tools": True, "status": {"staged": [], "unstaged": [], "untracked": []}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "モジュールではありません"}},
]
