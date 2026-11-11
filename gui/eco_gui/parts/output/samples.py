SAMPLES = [
    {"name": "ふつう", "props": {"lines": ["構成しています…", "ビルドしています…", "成功しました"]}},
    {"name": "まだない", "props": {}},
    {"name": "実行中", "props": {"title": "ビルド", "state": "run", "kind": "build", "lines": ["構成しています…", "[1/4] Building CXX object Calc/Add.cpp.obj"]}},
    {"name": "失敗（エラーと警告の色と数）", "props": {"title": "ビルド", "state": "bad", "kind": "build", "lines": [
        "[1/4] Building CXX object Calc/Add.cpp.obj", "C:/work/Calc/src/Add.cpp(12,5): error C2065: 'x': 定義されていない識別子です",
        "C:/work/Calc/src/Add.cpp(20,1): warning C4100: 'y': 引数は使われていません", "Build FAILED.", "1 Error(s)"]}},
    {"name": "試験の結果（1件ずつの ✗ ✓ -）", "props": {"title": "テスト", "state": "ok", "kind": "test", "lines": ["collected 4 items"], "result": {
        "configuration": "Debug", "passed": 2, "failed": 1, "skipped": 1, "cases": [
            {"name": "tests/test_app.py::test_add", "status": "passed"}, {"name": "tests/test_app.py::test_sub", "status": "failed"},
            {"name": "tests/test_app.py::test_mul", "status": "passed"}, {"name": "tests/test_app.py::test_slow", "status": "skipped"}]}}},
    {"name": "ビルドの結果（成果物）", "props": {"title": "ビルド", "state": "ok", "kind": "build", "fill": True, "lines": ["ビルドしています…"], "result": {
        "configuration": "Release", "artifacts": ["dist/calc-1.0-py3-none-any.whl", "dist/calc-1.0.tar.gz"]}}},
    {"name": "実行の結果（終了コード）", "props": {"title": "実行", "state": "ok", "kind": "run", "lines": [], "result": {"returncode": 3, "output": "引数が足りません\n"}}},
    {"name": "ファイルと行のリンク", "props": {"title": "ビルド", "state": "bad", "kind": "build", "lines": [
        "C:\\work\\Calc\\src\\Add.cpp(12,5): error C2065: 'x': 定義されていない識別子です。",
        "src/app.py:7:1: warning: unused import", '  File "tests/test_app.py", line 31, in test_add']}},
    {"name": "提出前の確認", "props": {"title": "提出前の確認", "state": "ok", "kind": "check", "result": {"items": [
        {"name": "generated", "ok": True, "detail": ""}, {"name": "build", "ok": True, "detail": ""}, {"name": "test", "ok": False, "detail": "1 failed, 12 passed"}]}}},
]
