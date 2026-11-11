"""ダブルクリックで、GUIFrameWork の上の新しい GUI（eco_gui）のハブを開く（コマンドプロンプトを出さない）。

中継地点を裏で起こし、ハブの窓を開く。もう動いていれば、ハブを前に出すだけ。
起こす前に、拡張コマンド ecobuild gui の入口（ecobuild-gui）がなければ置く（オペレーターとの会話・外からの GUI の操作に使う）。
開けなかったときは、理由を窓で知らせる（GUIFrameWork が入っていない・ecobuild の版が合わない 等）。
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def tell(message: str) -> None:
    """理由を知らせる。Windows では窓で（コマンドプロンプトがないので）、ほかでは標準エラーへ。"""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "ECOBuild GUI", 0x10)
    else:
        print(message, file=sys.stderr)


def main() -> int:
    try:
        import guiframework  # noqa: F401
    except ImportError:
        tell(f"GUIFrameWork が入っていません。\n{sys.executable} -m pip install -r {HERE / 'eco_gui' / 'requirements.txt'}")
        return 1
    try:  # ecobuild gui の入口。置けなくても、窓は開く
        sys.path.insert(0, str(HERE))
        import eco_gui_setup

        eco_gui_setup.place_command(shutil.which("ecobuild"))
    except Exception:
        pass
    from guiframework.procs import console_python

    # 窓のない pythonw のままでは、ecobuild を呼ぶたびにコマンドプロンプトの窓が出る。隣の python を、窓のないコンソールで起こす
    # （その先の中継地点・ecobuild は、この見えないコンソールを受け継ぐ）
    flags = 0x08000000 if sys.platform == "win32" else 0
    done = subprocess.run([console_python(sys.executable), "-m", "eco_gui.app", "serve", "--background", "--screen", "hub", "--json"],
                          cwd=HERE, creationflags=flags, stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        try:
            error = json.loads(done.stdout.strip().splitlines()[-1])["error"]
            message = error["message"] + (f"\n{error['hint']}" if error.get("hint") else "")
        except (ValueError, IndexError, KeyError, TypeError):
            message = (done.stderr or done.stdout or "").strip() or f"終了コード {done.returncode}"
        tell(f"新しい GUI を開けませんでした。\n{message}")
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
