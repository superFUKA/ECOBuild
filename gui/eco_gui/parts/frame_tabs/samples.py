SAMPLES = [
    {"name": "タブ（2つ目を出している）", "props": {
        "workspaces": [
            {"name": "12", "path": "C:/work/Calc/.ecobuild/w/12", "branch": "task/12-login", "task": 12, "account": None, "review": None},
            {"name": "15", "path": "C:/work/Calc/.ecobuild/w/15", "branch": "task/15-search", "task": 15, "account": None, "review": None},
            {"name": "review-31", "path": "C:/work/Calc/.ecobuild/w/review-31", "branch": "review/31", "task": None, "account": None, "review": 14}],
        "tasks": [{"number": 12, "title": "ログイン画面を作る"}, {"number": 15, "title": "検索を速くする"}],
        "current": "C:/work/Calc/.ecobuild/w/15",
        "vs2026": {"can": True, "reason": ""}, "vs2022": {"can": False, "reason": "Visual Studio 2022 が、この PC に見つかりません。"}}},
    {"name": "閉じたタブがある", "props": {
        "workspaces": [
            {"name": "12", "path": "C:/work/Calc/.ecobuild/w/12", "branch": "task/12-login", "task": 12, "account": None, "review": None},
            {"name": "15", "path": "C:/work/Calc/.ecobuild/w/15", "branch": "task/15-search", "task": 15, "account": None, "review": None}],
        "tasks": [{"number": 12, "title": "ログイン画面を作る"}],
        "current": "C:/work/Calc/.ecobuild/w/12", "closed": ["C:/work/Calc/.ecobuild/w/15"]}},
    {"name": "出しているタブがない（全部閉じた）", "props": {
        "workspaces": [
            {"name": "12", "path": "C:/work/Calc/.ecobuild/w/12", "branch": "task/12-login", "task": 12, "account": None, "review": None}],
        "tasks": [{"number": 12, "title": "ログイン画面を作る"}], "closed": ["C:/work/Calc/.ecobuild/w/12"]}},
    {"name": "作業空間がない", "props": {"workspaces": [], "tasks": []}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "読めない", "props": {"error": "モジュールではありません"}},
]
