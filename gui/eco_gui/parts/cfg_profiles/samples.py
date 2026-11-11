SAMPLES = [
    {"name": "C++（オプション・Project ごとの上書き）", "props": {"kind": "cpp", "data": {"selected": "release", "profiles": {
        "debug": {"configuration": "Debug", "shared": False, "parallel": 4, "options": {}, "projects": {}},
        "release": {"configuration": "Release", "shared": True, "parallel": 8,
                    "options": {"cpp_standard": 23, "generator": "Ninja Multi-Config", "test_continue_on_failure": False, "fetch_git": False},
                    "projects": {"Core": {"type": "static", "cpp_standard": 20}, "CoreTest": {"test_parallel": 4}}},
    }}}},
    {"name": "Python（並列数）", "props": {"kind": "python", "data": {"selected": None, "profiles": {
        "release": {"configuration": "Release", "parallel": 4}}}}},
    {"name": "そのほかの型", "props": {"kind": "generic", "data": {"selected": "ci", "profiles": {"ci": {"configuration": "Release"}}}}},
    {"name": "まだない", "props": {"kind": "cpp", "data": {"selected": None, "profiles": {}}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "ecobuild.toml を読めません"}},
]
