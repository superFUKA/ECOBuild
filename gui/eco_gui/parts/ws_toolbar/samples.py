SAMPLES = [
    {"name": "タスクブランチ（遅れ・衝突の見込み）", "props": {
        "status": {"branch": "task/12-login", "task": 12, "base": "main", "base_at": "0123abcdef"},
        "remote": {"base_behind": 3, "base_conflicts": ["src/app.py"]},
        "profiles": {"profiles": {"fast": {"configuration": "Debug"}, "ship": {"configuration": "Release"}}, "selected": "fast"},
        "account": {"login": "octocat", "role": "write", "workspace_account": "octo-ai"},
        "container": {"container": True, "state": "running", "image": "ecobuild-calc:1"}, "last_test": {"passed": 3, "failed": 1, "cases": [{"name": "tests/test_app.py::test_add", "status": "failed"}]}}},
    {"name": "タスクブランチ（遅れ）", "props": {
        "status": {"branch": "task/12-login", "task": 12, "base": "feature/mvp", "base_at": "99072a3f77"}, "remote": {"base_behind": 1},
        "configuration": "Release", "module_type": "cpp", "account": {"login": "octocat", "role": "admin"}, "container": {"container": False, "docker_ready": True}}},
    {"name": "ほかのブランチ", "props": {"status": {"branch": "main", "task": None}, "account": {"login": "octocat"}, "container": {"container": False, "docker_ready": False, "docker_detail": "Docker がありません"}}},
    {"name": "衝突で止まっている", "props": {"status": {"branch": "task/12-login", "task": 12, "base": "main", "merging": True}}},
    {"name": "まだ読めていない", "props": {}},
]
