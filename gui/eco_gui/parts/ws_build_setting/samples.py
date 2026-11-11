SAMPLES = [
    {"name": "C++（ビルド設定を使っている・対象を選んでいる）", "props": {
        "profiles": {"selected": "fast", "profiles": {"fast": {"configuration": "Debug", "shared": False}, "ship": {"configuration": "Release", "shared": True}}},
        "configuration": "", "module_type": "cpp",
        "projects": [{"name": "Calc", "kind": "static_library"}, {"name": "CalcTest", "kind": "test"}, {"name": "App", "kind": "executable"}],
        "target": "App", "arguments": "--size 3"}},
    {"name": "この窓で構成を選んでいる", "props": {
        "profiles": {"selected": "fast", "profiles": {"fast": {"configuration": "Debug", "shared": False}}},
        "configuration": "Release", "module_type": "python"}},
    {"name": "ビルド設定がない（Python）", "props": {"profiles": {"selected": None, "profiles": {}}, "module_type": "python"}},
    {"name": "ビルド設定を使っていない", "props": {
        "profiles": {"selected": None, "profiles": {"fast": {"configuration": "Debug", "shared": False}}}, "module_type": "cpp", "projects": []}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "ビルド設定を読めませんでした。"}},
]
