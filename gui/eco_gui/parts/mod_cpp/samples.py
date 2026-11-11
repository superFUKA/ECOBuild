SAMPLES = [
    {"name": "Project（テストはライブラリの下・main・依存先へのリンク）", "props": {
        "view": "projects",
        "projects": [
            {"name": "Game", "kind": "executable", "directory": "Game", "links": ["Engine", "Math"]},
            {"name": "Engine", "kind": "static_library", "directory": "libs/Engine", "links": ["Math/Core"]},
            {"name": "EngineTest", "kind": "test", "directory": "libs/EngineTest", "links": ["Engine"]},
            {"name": "EngineBench", "kind": "benchmark", "directory": "libs/EngineBench", "links": ["Engine", "Math"]},
            {"name": "Plugin", "kind": "shared_library", "directory": "Plugin", "links": []}],
        "deps": [{"name": "Math", "url": "https://github.com/acme/Math.git", "recorded": "abc12345", "local": "abc12345", "state": "aligned"}],
        "settings": {"main_project": "Engine", "msvc_runtime": "dll", "folders": None, "templates": {}}}},
    {"name": "Project（なし）", "props": {"view": "projects", "projects": []}},
    {"name": "依存先（状態の色・使っている Project・依存関係の図）", "props": {
        "view": "deps",
        "projects": [{"name": "Game", "kind": "executable", "directory": "Game", "links": ["Math", "Net/Http"]}],
        "deps": [
            {"name": "Math", "url": "https://github.com/acme/Math.git", "recorded": "abc1234567", "local": "abc1234567", "branch": None, "state": "aligned"},
            {"name": "Net", "url": "https://github.com/acme/Net.git", "recorded": "def1234567", "local": "999aaa1234", "branch": "main", "state": "differs"},
            {"name": "Draw", "url": "https://github.com/acme/Draw.git", "recorded": "777bbb1234", "local": "777bbb1234", "branch": "task/3-fix", "state": "modified"},
            {"name": "Audio", "url": "https://github.com/acme/Audio.git", "recorded": "555ccc1234", "local": None, "branch": None, "state": "missing"}],
        "tree": {"module": "Game", "direct": ["Math", "Net", "Audio"], "nodes": [
            {"name": "Math", "revision": "abc1234567", "present": True, "depends_on": ["Core"]},
            {"name": "Net", "revision": "def1234567", "present": True, "depends_on": ["Core", "Math"]},
            {"name": "Core", "revision": "0123456789", "present": True, "depends_on": []},
            {"name": "Audio", "revision": "555ccc1234", "present": False, "depends_on": []}]}}},
    {"name": "依存先（GitHub と照らし合わせた・版を選ぶ）", "props": {
        "view": "deps", "fetched": True,
        "deps": [
            {"name": "Math", "url": "https://github.com/acme/Math.git", "recorded": "abc1234567", "local": "abc1234567", "state": "aligned",
             "remote": "ok", "latest": "fff0000111"},
            {"name": "Net", "url": "https://github.com/acme/Net.git", "recorded": "def1234567", "local": "def1234567", "state": "aligned",
             "remote": "moved", "moved_to": "acme/Network", "latest": "def1234567"},
            {"name": "Old", "url": "https://github.com/acme/Old.git", "recorded": "111aaa1234", "local": "111aaa1234", "state": "working", "remote": "gone"}],
        "versions": {"name": "Math", "recorded": "abc1234567", "default_branch": "main", "branch": "main", "branches": ["main", "dev"],
                     "tags": [{"name": "v1.2.0", "sha": "abc1234567", "date": "2026-11-01T10:00:00+09:00"}],
                     "commits": [{"sha": "fff0000111", "date": "2026-11-09T18:02:00+09:00", "subject": "行列の掛け算を速くする", "tags": []},
                                 {"sha": "abc1234567", "date": "2026-11-01T10:00:00+09:00", "subject": "1.2.0", "tags": ["v1.2.0"]}]}}},
    {"name": "依存先（なし）", "props": {"view": "deps", "deps": []}},
    {"name": "全般", "props": {"view": "general", "settings": {
        "main_project": "Engine", "msvc_runtime": "dll",
        "folders": {"projects": "Projects", "linked_projects": "LinkedProjects", "external": "External"}, "templates": {}}}},
    {"name": "全般（main なし）", "props": {"view": "general", "settings": {"main_project": None, "msvc_runtime": None, "folders": None, "templates": {}}}},
    {"name": "ファイルテンプレート", "props": {"view": "templates", "settings": {"main_project": "Engine", "templates": {
        "header": {"path": ".ecobuild/.cppbuild/templates/header.h", "builtin": True},
        "source": {"path": ".ecobuild/.cppbuild/templates/source.cpp", "builtin": True},
        "widget": {"path": "templates/widget.h", "builtin": False}}}}},
    {"name": "読み込み中", "props": {"view": "projects", "loading": True}},
    {"name": "誤り", "props": {"view": "deps", "error": "project は型 cpp のモジュールのコマンドです（このモジュールの型：python）。"}},
]
