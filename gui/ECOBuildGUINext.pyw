"""ダブルクリックで、GUIFrameWork の上の新しい GUI（eco_gui）のハブを開く（コマンドプロンプトを出さない）。

中継地点を裏で起こし、ハブの窓を開く。もう動いていれば、ハブを前に出すだけ。
--module <モジュールのフォルダか名前>：ハブではなく、そのモジュールの窓を開く（開いていれば、今のページのまま前に出す）。
モジュールのショートカット・タスクバーにピン留めしたモジュールの窓は、これで開く（next_commands.py の shortcut・electron/main.js）。
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


def module_of(given: str) -> str:
    """--module の場所：フォルダならそのまま。名前なら、この PC のモジュールの一覧から（next_gui.module_folder）。"""
    import next_gui

    def ecobuild(args):
        done = subprocess.run([shutil.which("ecobuild") or "ecobuild", *args, "--json"], capture_output=True, encoding="utf-8",
                              errors="replace", stdin=subprocess.DEVNULL, creationflags=0x08000000 if sys.platform == "win32" else 0)
        return json.loads(done.stdout.strip().splitlines()[-1])

    return next_gui.module_folder(given, ecobuild)


def open_module(root: str) -> None:
    """モジュールの窓を開く（そのモジュールの窓が開いていれば、切り替えずに前に出す：ハブの一覧から開くのと同じ。表示の CLI の open --keep）。"""
    from guiframework.procs import console_python

    done = subprocess.run([console_python(sys.executable), "-m", "eco_gui.app", "open", "--keep", "--json", "--", "frame-workspaces",
                           f"module={root}"], cwd=HERE, creationflags=0x08000000 if sys.platform == "win32" else 0,
                          stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        try:
            error = json.loads(done.stdout.strip().splitlines()[-1])["error"]
            message = error["message"]
        except (ValueError, IndexError, KeyError, TypeError):
            message = (done.stderr or done.stdout or "").strip() or f"終了コード {done.returncode}"
        raise RuntimeError(message)


def main(argv: list[str] | None = None) -> int:
    words = list(sys.argv[1:] if argv is None else argv)
    module = words[words.index("--module") + 1] if "--module" in words[:-1] else ""
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
    if module:
        try:
            module = module_of(module)
        except Exception as error:  # 見つからない・ecobuild を呼べない
            tell(f"モジュールの窓を開けませんでした。
{getattr(error, 'message', None) or error}")
            return 1
    done = subprocess.run([console_python(sys.executable), "-m", "eco_gui.app", "serve", "--background",
                           *(() if module else ("--screen", "hub")), "--json"],
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
