SAMPLES = [
    {"name": "既定の場所", "props": {"path": "Calc/src/parse/Lexer.cpp", "plan": {"paths": ["CalcTest/src/parse/LexerTest.cpp"]},
                                 "files": ["Calc/src/parse/Lexer.cpp", "CalcTest/src/AddTest.cpp", "CalcTest/src/main.cpp"]}},
    {"name": "既にある", "props": {"path": "Calc/src/Add.cpp", "plan": {"paths": ["CalcTest/src/AddTest.cpp"]},
                                "files": ["Calc/src/Add.cpp", "CalcTest/src/AddTest.cpp"]}},
    {"name": "読み込み中", "props": {"path": "Calc/src/Add.cpp", "loading": True}},
    {"name": "誤り", "props": {"path": "Calc/src/Add.cpp", "error": "テスト用のProject（CalcTest）がありません"}},
]
