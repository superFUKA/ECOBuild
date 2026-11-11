SAMPLES = [
    {"name": "早送り（取り込める）", "props": {"plan": {
        "name": "dev", "into": "main", "method": "fast-forward", "commit_count": 3,
        "commits": [
            {"sha": "47ea8c4deee3ef3cbbff63869ff5b09afe2ea572", "subject": "ログイン画面を足す (#12)", "author": "octocat", "date": "2026-11-10T09:37:06+09:00"},
            {"sha": "4ca4aba0000000000000000000000000000000aa", "author": "hubot", "date": "2026-11-09T18:02:00+09:00",
             "subject": "検索の欄を、入力のたびに絞り込むようにする（長い件名は、行の中で切って「…」にする。窓が狭いときも、行は1行のまま） (#20)"},
            {"sha": "0ce7ca50000000000000000000000000000000bb", "subject": "設定を保存する", "author": "octocat", "date": "2026-11-08T11:20:00+09:00"}],
        "files": ["src/app.py", "src/login.py", "tests/test_login.py"], "file_count": 3, "conflicts": [], "resolved": [], "allowed": True, "owners": ""}}},
    {"name": "マージコミット（コミットが多い・自動で直る衝突・取り込めるのは別の人）", "props": {"plan": {
        "name": "dev", "into": "release", "method": "merge", "commit_count": 40,
        "commits": [
            {"sha": "a000000000000000000000000000000000000001", "subject": "1つ目", "author": "octocat", "date": "2026-11-10T09:00:00+09:00"},
            {"sha": "a000000000000000000000000000000000000002", "subject": "2つ目", "author": "octocat", "date": "2026-11-10T08:00:00+09:00"},
            {"sha": "a000000000000000000000000000000000000003", "subject": "3つ目", "author": "hubot", "date": "2026-11-09T09:00:00+09:00"},
            {"sha": "a000000000000000000000000000000000000004", "subject": "4つ目", "author": "hubot", "date": "2026-11-09T08:00:00+09:00"},
            {"sha": "a000000000000000000000000000000000000005", "subject": "5つ目", "author": "octocat", "date": "2026-11-08T09:00:00+09:00"},
            {"sha": "a000000000000000000000000000000000000006", "subject": "6つ目", "author": "octocat", "date": "2026-11-08T08:00:00+09:00"},
            {"sha": "a000000000000000000000000000000000000007", "subject": "7つ目", "author": "mona", "date": "2026-11-07T09:00:00+09:00"},
            {"sha": "a000000000000000000000000000000000000008", "subject": "8つ目", "author": "mona", "date": "2026-11-07T08:00:00+09:00"},
            {"sha": "a000000000000000000000000000000000000009", "subject": "9つ目", "author": "mona", "date": "2026-11-06T09:00:00+09:00"},
            {"sha": "a00000000000000000000000000000000000000a", "subject": "10個目", "author": "mona", "date": "2026-11-06T08:00:00+09:00"}],
        "files": ["src/app.py", "src/login.py"], "file_count": 12, "conflicts": [], "resolved": ["CMakeLists.txt"], "allowed": False,
        "owners": "release を作った octocat と管理者"}}},
    {"name": "衝突する", "props": {"plan": {
        "name": "dev", "into": "main", "method": "conflict", "commit_count": 2,
        "commits": [
            {"sha": "47ea8c4deee3ef3cbbff63869ff5b09afe2ea572", "subject": "ログイン画面を足す (#12)", "author": "octocat", "date": "2026-11-10T09:37:06+09:00"},
            {"sha": "0ce7ca50000000000000000000000000000000bb", "subject": "設定を保存する", "author": "octocat", "date": "2026-11-08T11:20:00+09:00"}],
        "files": ["src/app.py", "README.md", "src/util/text.py"], "file_count": 3, "conflicts": ["src/app.py", "README.md"], "resolved": [],
        "allowed": True, "owners": ""}}},
    {"name": "取り込み済み", "props": {"plan": {
        "name": "dev", "into": "main", "method": "up-to-date", "commits": [], "commit_count": 0, "files": [], "file_count": 0, "conflicts": [], "resolved": [],
        "allowed": True, "owners": ""}}},
    {"name": "取り込み先を選ぶ前", "props": {}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "dev は GitHub にありません。Push してから取り込んでください。"}},
]
