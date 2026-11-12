"""新しい GUI（gui/eco_gui。GUIFrameWork の上）への道：外から頼まれた GUI の操作を、新しい GUI の表示の CLI へつなぐ。

新しい GUI は、表示の CLI（python -m eco_gui.app <命令>：open・tree・emit・windows・notify …）で、外から画面を開く・
今の表示を読む・人の代わりに入力を出すことができる。ここは、ecobuild gui・MCP の「GUIの操作」を、その命令に直すだけ
（人が窓でするのと同じ道を通る。ここだけの処理は持たない）。

どちらの GUI に頼むかの決まりは ecobuild_gui.target()。使うのは Python の標準ライブラリだけ（表示の CLI は、
GUIFrameWork の入った Python で別のプロセスとして呼ぶ）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import actions
from actions import Action, Param

HERE = Path(__file__).resolve().parent
NEXT, CLASSIC = "next", "classic"
TARGET_ENV = "ECOBUILD_GUI_TARGET"            # どちらの GUI に頼むかを、はっきり決める（next・classic）
PYTHON_ENV = "ECOBUILD_GUI_NEXT_PYTHON"       # 表示の CLI を動かす Python（GUIFrameWork の入ったもの）
INSIDE_ENV = ("GUIFRAMEWORK_WINDOW", "GUIFRAMEWORK_RUN")   # 新しい GUI が、実行するコマンドに渡す環境変数


class Refused(Exception):
    """できなかった。code・message・hint は ecobuild の JSON の error と同じ（ecobuild_gui が Failure にする）。"""

    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code, self.message, self.hint = code, message, hint


def chosen() -> str | None:
    """動いているかを調べずに決まる頼み先：はっきり決めてある（TARGET_ENV）か、新しい GUI の中から頼まれた。なければ None。"""
    given = os.environ.get(TARGET_ENV, "").strip().lower()
    if given in (NEXT, CLASSIC):
        return given
    return NEXT if any(os.environ.get(name) for name in INSIDE_ENV) else None


# 表示の CLI ---------------------------------------------------------------------------------------------------------
def python() -> str | None:
    """表示の CLI を動かす Python：環境変数、今の Python（GUIFrameWork が入っていれば）、インストーラーが作った venv の順。"""
    given = os.environ.get(PYTHON_ENV)
    if given:
        return given
    if importlib.util.find_spec("guiframework") is not None:
        return sys.executable
    import eco_gui_setup
    found = eco_gui_setup.python_of(eco_gui_setup.default_venv())
    return str(found) if found.is_file() else None


def display(command: str, *words: str, options: tuple[str, ...] = (), by: str | None = None, timeout: float = 120) -> object:
    """表示の命令を1つ送り、結果（result）を返す。できなければ Refused（code は表示の CLI の error.code：no_display 等）。

    words は位置引数（「--」の後ろに置くので、- で始まる文もそのまま渡る）。by は依頼元（窓の枠に出る）。
    """
    program = python()
    if program is None:
        raise Refused("no_display", "新しい GUI（eco_gui）が準備されていません。",
                      "インストーラーか、python gui/eco_gui_setup.py で準備します。")
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if by and not env.get("GUIFRAMEWORK_REQUESTER"):
        env["GUIFRAMEWORK_REQUESTER"] = by
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        done = subprocess.run([program, "-m", "eco_gui.app", command, *options, "--json", "--", *words], cwd=HERE, env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8", errors="replace",
                              timeout=timeout, creationflags=flags)
        lines = done.stdout.strip().splitlines()
        document = json.loads(lines[-1]) if lines else None
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise Refused("gui_error", f"新しい GUI に頼めませんでした：{error}") from None
    if not isinstance(document, dict):
        tail = (done.stderr or "").strip().splitlines()[-3:]
        raise Refused("gui_error", "新しい GUI に頼めませんでした。" + ("\n" + "\n".join(tail) if tail else ""))
    if document.get("ok"):
        return document.get("result")
    error = document.get("error") or {}
    raise Refused(str(error.get("code") or "gui_error"), str(error.get("message") or "新しい GUI が断りました。"), error.get("hint"))


def running() -> bool:
    """新しい GUI（の中継地点）が動いているか。"""
    if python() is None:
        return False
    try:
        display("windows", timeout=20)
        return True
    except Refused:
        return False


# 新しい GUI での GUIの操作 ---------------------------------------------------------------------------------------------
# 今の GUI の画面の名前（open の page）→ 新しい GUI の画面。新しい GUI の画面の名前は screens（gui_screens）で分かる
PAGE_SCREENS = {"workspace": "frame-workspaces", "tasks": "tasks", "branches": "branches", "agents": "agents",
                "manage": "members", "modinfo": "overview", "settings": "settings", "help": "help"}
# 今の GUI と同じ操作（引数も同じ）：どちらの GUI でも同じ言い方で頼める
SAME = ("run", "folder", "vs", "notify")

ACTIONS: dict[str, Action] = {a.name: a for a in (
    *(actions.ACTIONS[name] for name in SAME),
    Action("open", "GUIの画面（ハブ・モジュールの窓）を開くか、前に出します。「〇〇を開いて」「〇〇の開発環境」はこれ（module に作業空間の場所か名前）。",
           "module を省くとハブ。module はモジュールのフォルダ（このPCの作業空間）か、モジュール名。screen に画面の名前（一覧は screens）。"
           "省くとモジュールの概要。同じ画面が開いていれば前に出します。タブ・選ぶタスクは開いた後に tree で読み、人に案内します。",
           (Param("module", "モジュール（フォルダか名前）。省くとハブ"),
            Param("screen", "開く画面の名前（screens の name。例：tasks・branches・submissions・operator）"),
            Param("page", "今までの GUI の画面の名前（screen を省いたとき、同じ役目の画面に読み替える）", choices=actions.PAGES),
            Param("args", "画面のほかの引数（名前=値 の並び。画面ごとの引数は screens の args）", "array"))),
    Action("screens", "新しい GUI の画面の一覧（名前・説明・引数）。open の screen に渡す名前を調べます。", effect="read"),
    Action("windows", "開いている窓と、それぞれが今表示しているもの（画面・引数・モジュール・題）。人が今見ている窓に looking: true。"
                      "中に重ねた窓は parent 付き。", effect="read"),
    Action("tree", "窓の今の表示を読みます：部品の木（それぞれの表示・使えない理由・出せる入力）・共有の値・実行中のコマンド。"
                   "人が見ているものを、そのまま読めます。", "",
           (Param("window", "窓の ID（windows の id。省くと、人が今見ている窓）"),), effect="read"),
    Action("emit", "人の代わりに、窓の部品へ入力を出します（ボタンを押す・行を選ぶ・欄に書く）。人が窓でするのと同じ道を通ります。",
           "target は <窓>/<部品のID>、output は tree の outputs にある名前。押したボタンが ECOBuild を変えるなら、変わります"
           "（確認の要る操作は、窓の前の人が答えるまで実行されません）。",
           (Param("target", "部品（<窓の ID>/<部品の ID>）", required=True),
            Param("output", "出力の名前（tree の outputs。ボタンなら pressed）", required=True),
            Param("payload", "出力の中身（名前=値 の並び）", "array"))),
)}

# 話し言葉の例（新しい GUI だけの操作。どちらの GUI でも同じ操作の例は actions.EXAMPLES）
EXAMPLES = (
    ("「提出の画面出して」「ECOSTL のブランチ見せて」", "ecobuild gui open --module C:/ECO/ECOSTL --screen submissions ／ --screen branches（画面の名前は ecobuild gui screens）"),
    ("「この画面、何が出てる？」「どこを押せばいい？」", "ecobuild gui tree（人が今見ている窓の表示。ボタンの名前・押せない理由を読んで案内する）"),
    ("「オペレーターの画面」「会話の画面出して」", "ecobuild gui open --screen operator"),
)

# 新しい GUI にない、今の GUI の操作 → 代わりにできること
ELSEWHERE = {
    "activity": "最近の実行は、窓の tree の runs（実行中）で読めます。",
    "agents": "エージェントの様子は、ecobuild agent list・agent status で読めます（画面は screen: operator）。",
}


def check(name: str, params: dict) -> dict:
    if name not in ACTIONS:
        hint = ELSEWHERE.get(name) or ("エージェントの窓（タブ）は今までの GUI だけにあります。エージェントは ecobuild agent … で扱います。"
                                       if name in actions.ACTIONS else None)
        raise Refused("not_supported", f"新しい GUI に、GUIの操作 {name} はありません（{'・'.join(ACTIONS)}）。", hint)
    return actions.check(name, params, ACTIONS)


def module_folder(given: str, ecobuild) -> str:
    """モジュールの場所：フォルダならそのまま。名前なら、このPCのモジュールの一覧（ecobuild workspace list）から探す。"""
    path = Path(given).expanduser()
    if path.is_dir():
        return path.resolve().as_posix()
    document = ecobuild(["workspace", "list"])
    result = document.get("result") if document.get("ok") else None
    for entry in (result.get("modules") or []) if isinstance(result, dict) else []:
        where = str(entry.get("path") or "")
        names = {(entry.get("repository") or "").split("/")[-1].lower(), where.replace("\\", "/").rstrip("/").split("/")[-1].lower()}
        if where and given.lower() in names - {""}:
            return Path(where).as_posix()
    raise Refused("not_found", f"モジュール {given} が見つかりません。", "場所は ecobuild workspace list で確かめられます。")


def start() -> None:
    """新しい GUI（の中継地点）を裏で起こす。窓は、この後の頼み（open 等）が開く。"""
    display("serve", options=("--background",), timeout=60)


def act(name: str, params: dict, *, ecobuild, by: str | None = None) -> object:
    """GUIの操作を、新しい GUI に頼む。動いていなければ起こしてから頼む。
    ecobuild は、ecobuild <引数> --json の文書を返す関数（引数・場所・標準入力）。"""
    try:
        return _act(name, params, ecobuild=ecobuild, by=by)
    except Refused as refused:
        if refused.code != "no_display" or python() is None:   # 準備されていない（venv がない）なら、起こせない
            raise
    start()
    return _act(name, params, ecobuild=ecobuild, by=by)


def _act(name: str, params: dict, *, ecobuild, by: str | None = None) -> object:
    p = check(name, params)
    if name == "open":
        module = module_folder(p["module"], ecobuild) if p.get("module") else None
        screen = p.get("screen") or PAGE_SCREENS.get(p.get("page", "")) or ("overview" if module else "hub")
        opened = display("open", screen, *([f"module={module}"] if module else []), *p.get("args", []), by=by)
        return {"gui": NEXT, "screen": screen, **({"module": module} if module else {}), **(opened if isinstance(opened, dict) else {})}
    if name == "screens":
        return (display("describe", by=by) or {}).get("screens") or []
    if name == "windows":
        found = (display("windows", by=by) or {}).get("windows") or []
        return [{**w, **({"module": w["args"]["module"]} if isinstance(w.get("args"), dict) and w["args"].get("module") else {})}
                for w in found if isinstance(w, dict)]
    if name == "tree":
        return display("tree", options=("--window", p["window"]) if p.get("window") else (), by=by)
    if name == "emit":
        return display("emit", p["target"], p["output"], *p.get("payload", []), by=by, timeout=3600)
    if name == "notify":
        level = {"ok": "ok", "info": "info", "bad": "error"}[p.get("kind", "info")]
        display("notify", p["message"], options=("--level", level), by=by)
        return {"gui": NEXT}
    if name == "run":
        # ecobuild のコマンドは、そのまま実行する（新しい GUI の画面も、同じ ecobuild を呼ぶ）。変えたら、窓に読み直しを頼む
        document = ecobuild(p["args"], p.get("dir"), p.get("stdin"))
        try:
            display("refresh", by=by, timeout=20)
        except Refused:
            pass   # 窓がなければ、読み直すものもない
        return document
    # folder・vs：窓の外のアプリで開く（今の GUI と同じ関数。ecobuild にこれを行うコマンドはない）
    import app
    try:
        if name == "folder":
            return app.open_path(p["dir"], p.get("path", ""), p.get("reveal", False))

        class Cli:   # update_solution が使う形（run(場所, 引数)）
            def run(self, directory, args):
                return ecobuild(args, directory)

        app.update_solution(Cli(), p["dir"])
        if p.get("path"):
            return app.open_file_in_visual_studio(p["dir"], p["path"], p.get("version", "2026"))
        return app.open_in_visual_studio(p["dir"], p.get("version", "2026"))
    except app.GuiError as error:
        raise Refused("gui_error", str(error)) from None
