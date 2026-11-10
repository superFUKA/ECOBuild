"""ダブルクリックで、GUIFrameWork の上の新しい GUI（eco_gui）のハブを開く（コマンドプロンプトを出さない）。

中継地点を裏で起こし、ハブの窓を開く。もう動いていれば、ハブを前に出すだけ。
GUIFrameWork が入っていない Python では、入れ方を知らせて終わる（eco_gui/requirements.txt）。
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    try:
        import guiframework  # noqa: F401
    except ImportError:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None, f"GUIFrameWork が入っていません。\n{sys.executable} -m pip install -r {HERE / 'eco_gui' / 'requirements.txt'}",
            "ECOBuild GUI", 0x10)
        return 1
    flags = 0x08000000 if sys.platform == "win32" else 0  # コマンドプロンプトの窓を出さない
    return subprocess.run([sys.executable, "-m", "eco_gui.app", "serve", "--background", "--screen", "hub"],
                          cwd=HERE, creationflags=flags).returncode


if __name__ == "__main__":
    sys.exit(main())
