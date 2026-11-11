SAMPLES = [
    {"name": "このブランチの退避と、ほかのブランチの退避", "props": {
        "stashes": ["On task/12-login: 3つ目（長い説明は、行の中で切って「…」にする。長い説明は、行の中で切って「…」にする。長い説明は、行の中で切る）",
                    "On main: 試し", "WIP on task/12-login: abc1234 途中の変更", "On task/12-login: 1つ目", "On task/20-search: 検索の途中"],
        "status": {"branch": "task/12-login", "staged": [], "unstaged": ["a.py", "b.py"], "untracked": ["new.txt"]}}},
    {"name": "変更がない（退避できない）", "props": {
        "stashes": ["On task/12-login: 途中の変更"], "status": {"branch": "task/12-login", "staged": [], "unstaged": [], "untracked": []}}},
    {"name": "退避がない", "props": {"stashes": [], "status": {"branch": "task/12-login", "staged": [], "unstaged": ["a.py"], "untracked": []}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "退避した変更を読めませんでした。"}},
]
