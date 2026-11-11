SAMPLES = [
    {"name": "状態の色と印", "props": {
        "files": ["README.md", "src/app.py", "src/login.py", "src/old.py", "src/util/text.py", "src/util/new.py", "tests/test_app.py", ".github/workflows/ci.yml"],
        "missing": ["src/old.py"],
        "status": {"staged": ["src/login.py"], "unstaged": ["src/app.py", "src/old.py"], "untracked": ["src/util/new.py"], "conflicted": ["tests/test_app.py"]},
        "selected": "src/app.py"}},
    {"name": "サブプロジェクト（C++）", "props": {
        "files": ["README.md", "Calc/include/Calc/Add.h", "Calc/src/Add.cpp", "CalcTest/src/AddTest.cpp", "CalcApp/src/main.cpp", "ecobuild.toml"],
        "projects": [{"name": "Calc", "kind": "static_library", "directory": "Calc"}, {"name": "CalcTest", "kind": "test", "directory": "CalcTest"},
                     {"name": "CalcApp", "kind": "executable", "directory": "CalcApp"}],
        "status": {"unstaged": ["Calc/src/Add.cpp"]}}},
    {"name": "生成ファイル（目の印で出したところ。ふだんは隠す）", "props": {
        "files": ["README.md", "CMakeLists.txt", "src/app.cpp", "src/CMakeLists.txt"], "generated": ["CMakeLists.txt", "src/CMakeLists.txt"],
        "status": {"unstaged": ["src/CMakeLists.txt"]}}},
    {"name": "空", "props": {"files": []}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "モジュールではありません"}},
]
