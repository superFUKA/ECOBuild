SAMPLES = [
    {"name": "Python（フォルダー › ファイル › クラス › 試験。前に流した結果つき）", "props": {
        "rows": [{"name": "tests/test_app.py::test_add", "file": "tests/test_app.py"}, {"name": "tests/test_app.py::test_sub", "file": "tests/test_app.py"},
                 {"name": "tests/test_app.py::TestMul::test_zero", "file": "tests/test_app.py"}, {"name": "tests/unit/test_text.py::test_trim", "file": "tests/unit/test_text.py"},
                 {"name": "tests/unit/test_text.py::test_split", "file": "tests/unit/test_text.py"}],
        "checked": ["tests/unit", "tests/test_app.py::test_add"],
        "last": {"cases": [{"name": "tests/test_app.py::test_add", "status": "passed"}, {"name": "tests/test_app.py::test_sub", "status": "failed"},
                           {"name": "tests/unit/test_text.py::test_trim", "status": "skipped"}]}}},
    {"name": "C++（サブプロジェクト › Suite › Test）", "props": {
        "rows": [{"name": "CalcTest.Add.Small"}, {"name": "CalcTest.Add.Large"}, {"name": "CalcTest.Mul.Zero"}, {"name": "TextTest.Trim.Spaces"}],
        "checked": ["CalcTest.Add.*"]}},
    {"name": "空", "props": {"rows": [], "empty_text": "「試験の一覧を読む」を押すと、流せる試験が出ます（C++・Python）。"}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "この型は、試験の一覧を読めません"}},
]
