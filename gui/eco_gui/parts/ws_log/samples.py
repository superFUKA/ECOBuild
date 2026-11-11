SAMPLES = [
    {"name": "ブランチを選ぶ欄", "props": {"branches": [{"name": "main"}, {"name": "feature/login"}, {"name": "task/12-login"}], "branch": "feature/login",
                                  "commits": [{"sha": "abc1234def", "subject": "ログインの画面", "author": "octocat", "date": "2026-11-01T10:00:00+09:00"}]}},
    {"name": "ログ（印・選んでいる行）", "props": {"selected": "b2c3d4e5f6a7", "commits": [
        {"sha": "a1b2c3d4e5f6", "subject": "ログイン画面：入力の検査を足す (#31)", "author": "octocat", "date": "2026-11-10T09:12:00+09:00", "pull_request": 31, "issue": 12},
        {"sha": "b2c3d4e5f6a7", "subject": "設定の読み込みを直す", "author": "hubot", "date": "2026-11-09T18:40:00+09:00", "pull_request": None, "issue": 9},
        {"sha": "c3d4e5f6a7b8", "subject": "最初のコミット", "author": "octocat", "date": "2026-11-01T10:00:00+09:00", "pull_request": None, "issue": None}]}},
    {"name": "Push するコミット（短い一覧）", "props": {"mode": "push", "search": False, "short": True, "empty_text": "Pushするコミットはありません。", "commits": [
        {"sha": "d4e5f6a7b8c9", "subject": "検査の文言を直す", "author": "octocat", "date": "2026-11-11T08:00:00+09:00"},
        {"sha": "e5f6a7b8c9d0", "subject": "検査を足す", "author": "octocat", "date": "2026-11-11T07:30:00+09:00"}]}},
    {"name": "空", "props": {"commits": []}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "ブランチがありません"}},
]
