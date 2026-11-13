SAMPLES = [
    {"name": "ふつう", "props": {
        "files": ["README.md", "ecobuild.toml", "CMakeLists.txt", "src/main.cpp", "src/util/math.cpp", "src/util/math.h", "tests/test_math.cpp", "docs/old.md"],
        "generated": ["CMakeLists.txt"], "missing": ["docs/old.md"]}},
    {"name": "空", "props": {"files": []}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "git で読めません"}},
]
