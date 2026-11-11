SAMPLES = [
    {"name": "取り込みが止まっている（箇所が2つ・直したファイル・直せないファイル）", "props": {
        "data": {"stopped": "merge", "current": "このタスクブランチの側", "incoming": "取り込む側", "ready": False, "files": [
            {"path": "src/app.py", "remaining": 2, "reason": "", "reason_text": "", "pieces": [
                {"text": "def add(a, b):\n", "conflict": False},
                {"text": "<<<<<<< HEAD\n    return a + b\n||||||| base\n    return a\n=======\n    return a - b\n>>>>>>> origin/main\n",
                 "conflict": True, "line": 2, "current": "    return a + b\n", "incoming": "    return a - b\n", "base": "    return a\n",
                 "both": "    return a + b\n    return a - b\n", "both_incoming_first": "    return a - b\n    return a + b\n"},
                {"text": "\n\n", "conflict": False},
                {"text": "<<<<<<< HEAD\nprint('local')\n=======\n>>>>>>> origin/main\n", "conflict": True, "line": 11,
                 "current": "print('local')\n", "incoming": "", "base": None, "both": "print('local')\n", "both_incoming_first": "print('local')\n"},
            ]},
            {"path": "README.md", "remaining": 0, "reason": "", "reason_text": "", "pieces": [{"text": "# 計算\n直した中身\n", "conflict": False}]},
            {"path": "assets/logo.png", "remaining": 0, "reason": "binary", "reason_text": "バイナリのファイルです", "pieces": []},
        ]},
        "status": {"branch": "task/12-login"}}},
    {"name": "全部直した（続けられる）", "props": {
        "data": {"stopped": "rebase", "current": "作成元の側", "incoming": "自分のコミットの側", "ready": True, "files": [
            {"path": "README.md", "remaining": 0, "reason": "", "reason_text": "", "pieces": [{"text": "# 計算\n直した中身\n", "conflict": False}]},
        ]},
        "status": {"branch": "task/12-login"}}},
    {"name": "ここでは直せないファイル", "props": {
        "data": {"stopped": "merge", "current": "このタスクブランチの側", "incoming": "取り込む側", "ready": False, "files": [
            {"path": "assets/logo.png", "remaining": 0, "reason": "binary", "reason_text": "バイナリのファイルです", "pieces": []},
        ]}}},
    {"name": "衝突はない", "props": {"data": {"stopped": None, "current": "今の側", "incoming": "入ってくる側", "ready": False, "files": []}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "モジュールではありません"}},
]
