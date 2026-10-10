"""ダブルクリックで ECOBuild GUI を開く（コマンドプロンプトを出さない）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402

app.main()
