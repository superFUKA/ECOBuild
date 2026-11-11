SAMPLES = [
    {"name": "開けている（選んでいるブランチが取り込み先・早送り）", "props": {
        "branches": [
            {"name": "main", "base": None, "local": True, "remote": True, "is_task_branch": False},
            {"name": "dev", "base": "main", "local": True, "remote": True, "is_task_branch": False},
            {"name": "feature/long-name-of-a-branch-that-does-not-fit", "base": "dev", "local": True, "remote": True, "is_task_branch": False},
            {"name": "local-only", "base": "main", "local": True, "remote": False, "merged": False, "is_task_branch": False},
            {"name": "task/12-login", "base": "dev", "local": True, "remote": True, "is_task_branch": True}],
        "name": "main", "source": "dev", "into": "main", "open": True,
        "plan": {"name": "dev", "into": "main", "method": "fast-forward", "commit_count": 3}}},
    {"name": "向きを入れ替えた（選んでいるブランチが取り込むブランチ・衝突する）", "props": {
        "branches": [
            {"name": "main", "base": None, "local": True, "remote": True, "is_task_branch": False},
            {"name": "dev", "base": "main", "local": True, "remote": True, "is_task_branch": False}],
        "name": "dev", "source": "dev", "into": "main", "open": True,
        "plan": {"name": "dev", "into": "main", "method": "conflict", "commit_count": 2}}},
    {"name": "畳んでいる（取り込み済み）", "props": {
        "branches": [
            {"name": "main", "base": None, "local": True, "remote": True, "is_task_branch": False},
            {"name": "dev", "base": "main", "local": True, "remote": True, "is_task_branch": False}],
        "name": "main", "source": "dev", "into": "main", "open": False,
        "plan": {"name": "dev", "into": "main", "method": "up-to-date", "commit_count": 0}}},
    {"name": "GitHub にないブランチ", "props": {
        "branches": [
            {"name": "main", "base": None, "local": True, "remote": True, "is_task_branch": False},
            {"name": "local-only", "base": "main", "local": True, "remote": False, "merged": False, "is_task_branch": False}],
        "name": "local-only", "open": True}},
    {"name": "畳めないカード（取り込み・提出のページ）", "props": {
        "branches": [
            {"name": "main", "base": None, "local": True, "remote": True, "is_task_branch": False},
            {"name": "dev", "base": "main", "local": True, "remote": True, "is_task_branch": False}],
        "name": "dev", "side": "from", "source": "dev", "into": "main", "open": True, "foldable": False,
        "plan": {"name": "dev", "into": "main", "method": "merge", "commit_count": 12}}},
    {"name": "読み込み中", "props": {
        "branches": [
            {"name": "main", "base": None, "local": True, "remote": True, "is_task_branch": False},
            {"name": "dev", "base": "main", "local": True, "remote": True, "is_task_branch": False}],
        "name": "main", "source": "dev", "into": "main", "open": True, "loading": True}},
    {"name": "誤り", "props": {"branches": [], "name": "main", "open": True, "error": "ブランチを読めませんでした。"}},
]
