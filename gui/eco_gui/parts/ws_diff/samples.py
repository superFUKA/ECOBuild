SAMPLES = [
    {"name": "コミットの変更", "props": {"title": "ログイン画面：入力の検査を足す", "sha": "a1b2c3d4e5f6", "text": (
        "commit a1b2c3d4e5f6\nAuthor: octocat\n\n    ログイン画面：入力の検査を足す\n\n src/login.py | 3 ++-\n 1 file changed\n\n"
        "diff --git a/src/login.py b/src/login.py\nindex 111..222 100644\n--- a/src/login.py\n+++ b/src/login.py\n@@ -1,3 +1,4 @@\n def login(name):\n-    return name\n+    if not name:\n+        raise ValueError\n     return name\n"
        "diff --git a/tests/test_login.py b/tests/test_login.py\nnew file mode 100644\n--- /dev/null\n+++ b/tests/test_login.py\n@@ -0,0 +1,2 @@\n+def test_login():\n+    pass\n")}},
    {"name": "差分なし", "props": {"text": ""}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "コミットがありません"}},
]
