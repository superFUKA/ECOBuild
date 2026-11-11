SAMPLES = [
    {"name": "一覧（全部の絞り込み）", "props": {
        "view": "tasks", "me": "octocat",
        "tasks": [{"number": 12, "assignees": ["octocat", "hubot"], "milestone": "v1"}, {"number": 13, "assignees": []}],
        "sprints": [{"name": "Sprint 1", "start": "2026-10-19", "end": "2026-11-02"}, {"name": "Sprint 2", "start": "2026-11-02", "end": "2026-11-16"}],
        "milestones": [{"title": "v1"}], "start": {"assignee": "@me", "closed": True}}},
    {"name": "次にやる（担当者だけ）", "props": {"view": "task-next", "scope": "assignee", "tasks": [{"number": 12, "assignees": ["hubot"]}]}},
    {"name": "概要（絞り込みなし）", "props": {"view": "task-summary", "scope": "none"}},
]
