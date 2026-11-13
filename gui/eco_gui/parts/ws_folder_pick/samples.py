SAMPLES = [
    {"name": "2つを移す", "props": {"paths": ["src/a.py", "src/b.py"], "files": ["README.md", "src/a.py", "src/b.py", "src/util/text.py", "tests/test_a.py"],
                               "folders": ["docs/new"]}},
    {"name": "サブプロジェクトの中だけ", "props": {"paths": ["Calc/src/Add.cpp", "Calc/src/Sub.cpp"],
                                          "files": ["Calc/src/Add.cpp", "Calc/src/Sub.cpp", "Calc/src/ops/Mul.cpp", "CalcApp/src/main.cpp", "ecobuild.toml"],
                                          "projects": [{"name": "Calc", "directory": "Calc"}, {"name": "CalcApp", "directory": "CalcApp"}]}},
    {"name": "読み込み中", "props": {"paths": ["a.py"], "loading": True}},
    {"name": "誤り", "props": {"paths": ["a.py"], "error": "モジュールではありません"}},
]
