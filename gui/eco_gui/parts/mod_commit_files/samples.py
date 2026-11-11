SAMPLES = [
    {"name": "ふつう", "props": {"text": (
        "commit 99072a3f77e01ad00ea14b269e\nAuthor: octocat <octocat@example.com>\nDate:   2026-11-11 08:47:18 +0900\n\n    ログイン画面を直す (#281)\n---\n"
        " src/app.py  | 3 ++-\n docs/new.md | 2 ++\n old.txt     | 1 -\n 3 files changed, 4 insertions(+), 2 deletions(-)\n\n"
        "diff --git a/src/app.py b/src/app.py\nindex 1111111..2222222 100644\n--- a/src/app.py\n+++ b/src/app.py\n@@ -1,4 +1,5 @@\n import sys\n-print('old')\n"
        "+print('new')\n+print('more')\n \n"
        "diff --git a/docs/new.md b/docs/new.md\nnew file mode 100644\nindex 0000000..3333333\n--- /dev/null\n+++ b/docs/new.md\n@@ -0,0 +1,2 @@\n+# 新しい文書\n+本文\n"
        "diff --git a/old.txt b/old.txt\ndeleted file mode 100644\nindex 4444444..0000000\n--- a/old.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-いらない行\n")}},
    {"name": "差分のないコミット", "props": {"text": "commit abc\nAuthor: octocat\n\n    マージ"}},
    {"name": "空", "props": {"text": ""}},
    {"name": "読み込み中", "props": {"text": "", "loading": True}},
    {"name": "誤り", "props": {"text": "", "error": "コミットがありません"}},
]
