"""オペレーター：ECOBuild GUI の案内・操作係のエージェント（このPCに1つ。ecobuild gui operator・ecobuild gui ask）。

ファイルの名前は operator_kit（GUI のフォルダーは import の先頭に入るので、標準ライブラリの operator と重ならないように）。

できるのは、読むこと（重さが read の ecobuild のコマンド）と、GUI の操作（actions.py。ほかのエージェントへ文字を送る
agent-send は除く）だけ。ECOBuild の状態を変える操作・シェル・ファイルの編集はしない（変える操作を頼まれたら、その画面を
開いて案内する）。道具は MCP（ecobuild gui mcp --operator）だけで渡し、シェル・編集の道具は許可の設定で止める。

作業ディレクトリは GUI の置き場所（gui_home）の operator。起動のたびに、今のコマンドの一覧（ecobuild --help --json）と
GUI の操作の一覧から、指示（CLAUDE.md）・許可（.claude/settings.json）・MCP の設定（mcp.json）を作り直す。
使い方は3つ：run（この端末で動かして待つ。Electron の窓が裏で常駐させる）、start（新しい画面）、ask（画面を開かず1回話しかける。
Edge の窓の会話）。GUI は ecobuild を import しない（コマンドを呼ぶだけ）ので、ここも ecobuild のコマンドだけを使う。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import actions  # noqa: E402

HERE = Path(__file__).resolve().parent
PROGRAM = "ecobuild"
SERVER = "ecobuild-gui"                 # MCP のサーバーの名前（Claude Code の道具の名前は mcp__ecobuild-gui__<ツール>）
INSTRUCTIONS = "CLAUDE.md"
SETTINGS = Path(".claude") / "settings.json"
MCP_CONFIG = "mcp.json"
DEFAULT_COMMAND = ("claude",)
# 許さない道具：シェル（ecobuild の変える操作・git・gh に届く）とファイルの編集。道具は MCP だけ
DENY = ("Bash", "PowerShell", "Edit", "Write", "NotebookEdit")
# GUI の操作のうち、オペレーターに渡さないもの：何でも実行できる run と、ほかのエージェントに頼む（変える操作を人の指示として
# させる）agent-send
HIDDEN_ACTIONS = ("run",)
HIDDEN_EFFECTS = ("requested",)
# 付けると重さが上がるオプション（CLI の _effects と同じ。見るだけのコマンドでも、これが付けば断る）
RAISING_OPTIONS = ("--yes", "-y", "--discard-local", "--force", "--remove-workspaces", "--write")
STATUS_MARK = "\x1b]1337;ECOBuildAgentStatus={}\x07"   # Electron の窓が拾う印（status.js と同じ）


class Failure(Exception):
    """GUI の口（ecobuild gui・MCP）の誤り。code・message・hint は ecobuild の JSON の error と同じ。"""

    def __init__(self, code: str, message: str, hint: str | None = None, exit_code: int = 1):
        super().__init__(message)
        self.code, self.message, self.hint, self.exit_code = code, message, hint, exit_code


def directory() -> Path:
    import app       # gui_home（GUIの設定の場所）はサーバーと同じ決め方で
    return app.gui_home() / "operator"


# ecobuild のコマンド ------------------------------------------------------------------------------------------------
def ecobuild(args: list[str], *, timeout: float = 120) -> dict:
    """ecobuild <args> --json の結果の文書（動かせなければ ok: false）。"""
    try:
        done = subprocess.run([PROGRAM, *args, "--json"], capture_output=True, encoding="utf-8", errors="replace",
                              stdin=subprocess.DEVNULL, timeout=timeout)
        lines = done.stdout.strip().splitlines()
        return json.loads(lines[-1]) if lines else {"ok": False}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"ok": False}


_catalogs: dict[str, dict] = {}


def catalog(where: str | None = None) -> dict:
    """コマンドの一覧（ecobuild [-C 場所] --help --json の result。場所ごとに1回だけ読む）。"""
    key = where or ""
    if key not in _catalogs:
        document = ecobuild([*(["-C", where] if where else []), "--help"])
        _catalogs[key] = (document.get("result") or {}) if document.get("ok") else {}
    return _catalogs[key]


def effects(found: dict) -> dict[str, tuple[str, str]]:
    """一覧の実行できるコマンド（共通と型の）→ (重さ, 短い説明)。"""
    table: dict[str, tuple[str, str]] = {}

    def walk(nodes):
        for node in nodes or ():
            if node.get("runnable"):
                table[node["path"]] = (node.get("effect") or "change", node.get("summary") or "")
            walk(node.get("commands"))

    walk(found.get("commands"))
    for entry in (found.get("types") or {}).values():
        walk(entry.get("commands"))
    return table


def read_command(args: list[str], found: dict) -> str:
    """args（ecobuild の引数）が、重さが read のコマンドならその名前。そうでなければ Failure（断る理由付き）。"""
    if any(a in ("-C", "--directory") or a.startswith(("--directory=", "-C")) for a in args):
        raise Failure("usage_error", "場所は -C ではなく dir で渡してください。", exit_code=2)
    words = [a for a in args if not a.startswith("-")]
    options = [a.split("=")[0] for a in args if a.startswith("-")]
    table = effects(found)
    path = next((" ".join(words[:n]) for n in range(min(len(words), 3), 0, -1) if " ".join(words[:n]) in table), "")
    if not path:
        raise Failure("not_allowed", f"ecobuild {' '.join(words[:2])} は見るだけのコマンドではないので、オペレーターは使えません。",
                      "コマンドの名前は ecobuild_commands で確かめられます。")
    effect = table[path][0]
    raised = [o for o in options if o in RAISING_OPTIONS] or ([o for o in options if o != "--json"] if path == "module settings" else [])
    if effect != "read" or raised:
        raise Failure("not_allowed", f"ecobuild {path}{' ' + ' '.join(raised) if raised else ''} は ECOBuild を変える操作なので、"
                                     "オペレーターは実行しません。",
                      "その操作ができる画面を gui_open で開いて、ユーザーに案内してください。")
    return path


def style() -> str:
    """ユーザーが決めた話し方（ECOBuild の設定 operator_style）。"""
    document = ecobuild(["config", "get", "operator_style"], timeout=30)
    value = (document.get("result") or {}).get("value") if document.get("ok") else None
    return value.strip() if isinstance(value, str) else ""


# 指示書 ------------------------------------------------------------------------------------------------------------
RULES = """# ECOBuild オペレーター

あなたは ECOBuild GUI（GitHub のリポジトリ＝モジュールを、Issue＝タスク単位の流れで開発するツール ECOBuild の画面）の
**案内係** です。ユーザーが見たいもの・探しているものを、GUI を操作して画面に出し、ECOBuild の状態を読んで答えます。

**ECOBuild を変える操作はしません**（タスクを作る・始める・提出する・取り込む、モジュール・ブランチ・設定を変える、消す など）。
頼まれたら、その操作ができる画面を `gui_open` で開き（page・tab・task・command で、そのボタンや説明のある所まで）、
どこで何を押せばよいかを短く案内します。押すのはユーザーです。コードを書く・ファイルを作る・編集する・調べものも仕事ではありません
（「作業空間のエージェントに頼んでください」と返す）。

## 使える道具（これだけ。シェル・ファイルの編集は使えません）

- `gui_<操作>`：GUI の操作（画面を開く・移る、フォルダ・Visual Studio で開く、知らせ、エージェントの窓）。下の一覧。
- `ecobuild_read`：重さが「見る」の ecobuild のコマンドだけを実行する（args に引数、dir に場所）。ほかのコマンドは断られる。
  結果の `ok`・`error.message`・`error.hint` を読む。
- `ecobuild_commands`：コマンドの使い方（path に "task list" 等）。型のコマンド（build・deps 等）は、dir にその型のモジュールの場所。

## 読み方

- 言われたことは、まず ECOBuild の画面のこととして読む。対象を言わない頼みは ECOBuild のこと。
- 入力は音声の文字起こしのことがある（誤変換・言い淀み・言い直し・途中で切れた文）。音の近い言葉に読み替えてよい
  （「エコ STL」「エコエスティーエル」「SQL」→ ECOSTL）。
- 1回の発言に頼みがいくつも入っていることが多い。最初に全部の「操作×対象」を書き出す。
  「いや」「やっぱ」「じゃなくて」の後ろが正しい（打ち消された対象は外す）。
- 「〇〇を開いて」「〇〇を見せて」「〇〇出して」「〇〇の開発環境」は ECOBuild の画面で開くこと（gui_open）。
  エクスプローラー・Visual Studio は、そのアプリの名前を言われたときだけ（gui_folder・gui_vs）。
- 場所は、発言に付いてくる「今の作業空間」の一覧を使う。そこにないときだけ `ecobuild_read` の `workspace list` で探す。
  名前を言わないとき（「これ」「今の」「この画面の」）は、`gui_windows` の looking: true の窓のモジュール。
- 本当にどちらとも読めるときだけ、1行の文で聞き返す（選択肢の画面は出さない。声・リングでは答えにくい）。

## 報告のしかた

- 結果は **1〜3行で短く**。やったことを全部並べる。前置き・言い直しはいらない。
- 「〜しました」と言ってよいのは、その道具が成功したときだけ。失敗したら、エラーの内容とヒントを短く伝える。
- 変える操作を頼まれたら、実行したふりをせず「〇〇の画面の『△△』で行えます（開きました）」のように案内する。
"""

STYLE_NOTE = "口調・言い回し・呼び方だけを変える。決まり・報告の中身（結果・エラー・数字）は変えず、正確に伝える"

EXAMPLES = (
    ("「ECOSTL 今どうなってる？」「エコ STL の状況は」", "ecobuild_read：status と task status を読み、1〜2行で"),
    ("「ECOSTL のタスク見せて」", "gui_open（module に場所、page に tasks）。一覧を言葉で聞かれたら ecobuild_read：task list"),
    ("「次やるのどれ？」", "ecobuild_read：task next"),
    ("「12番始めて」「提出して」「ビルドして」（変える操作）",
     "gui_open でその画面（タスク管理・作業空間）を開き、どのボタンで行えるかを案内する（実行はしない）"),
    ("「差分見せて」「12番の差分」", "ecobuild_read：diff --gui ／ task diff 12 --gui（TortoiseGit で開く）"),
    ("「GitHub にあるモジュールは？」", "ecobuild_read：module list"),
)


def instructions(found: dict, examples=None, style_text: str = "") -> str:
    """指示書：決まり・話し言葉の例・使える GUI の操作と、見るだけのコマンドの一覧（コマンドの一覧 found から作る）。"""
    lines = [RULES]
    if style_text.strip():
        lines += ["## 話し方（ユーザーの指定）", "", style_text.strip(), "", f"（{STYLE_NOTE}）", ""]
    lines += ["## 例（言われたこと → すること）", ""]
    lines += [f"- {say} → {do}" for say, do in EXAMPLES]
    for say, do in examples if examples is not None else actions.EXAMPLES:
        if not any(f"gui {name}" in do for name in hidden_actions()):
            lines.append(f"- {say} → {do.replace('ecobuild gui ', 'gui_')}")
    lines += ["", "## GUI の操作（道具 gui_<操作>）", ""]
    lines += [f"- `gui_{a.name}`：{a.summary}" for a in operator_actions()]
    lines += ["", "## 見るだけのコマンド（ecobuild_read で使える。モジュールの中のものは dir に場所）", ""]
    lines += [f"- `{path}`：{summary}" for path, (effect, summary) in sorted(effects(found).items()) if effect == "read"]
    return "\n".join(lines) + "\n"


def hidden_actions() -> tuple[str, ...]:
    return tuple(a.name for a in actions.ACTIONS.values() if a.name in HIDDEN_ACTIONS or a.effect in HIDDEN_EFFECTS)


def operator_actions() -> list[actions.Action]:
    """オペレーターに渡す GUI の操作。"""
    return [a for a in actions.ACTIONS.values() if a.name not in hidden_actions()]


# 一式（指示・許可・MCP） ------------------------------------------------------------------------------------------
def python() -> str:
    return Path(sys.executable).as_posix()


def script() -> str:
    return (HERE / "ecobuild_gui.py").as_posix()


def prepare(found: dict | None = None, style_text: str | None = None) -> Path:
    """一式を置いて、その場所を返す（毎回作り直す。古い指示が残らないように）。"""
    folder = directory()
    (folder / SETTINGS).parent.mkdir(parents=True, exist_ok=True)
    text = instructions(catalog() if found is None else found, style_text=style() if style_text is None else style_text)
    settings = {"permissions": {"allow": [f"mcp__{SERVER}"], "deny": list(DENY)},
                "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command",
                                                           "command": f'"{python()}" "{script()}" operator-context'}]}]}}
    servers = {"mcpServers": {SERVER: {"command": python(), "args": [script(), "mcp", "--operator"]}}}
    _write(folder / INSTRUCTIONS, text)
    _write(folder / SETTINGS, json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
    _write(folder / MCP_CONFIG, json.dumps(servers, ensure_ascii=False, indent=2) + "\n")
    return folder


def _write(path: Path, text: str) -> None:
    if not path.is_file() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8", newline="\n")


def _command(command: tuple[str, ...]) -> list[str]:
    """起動するコマンド。Claude Code なら、考える量を少なく（--effort low）、道具は一式の MCP だけ。"""
    command = tuple(command) or DEFAULT_COMMAND
    program = shutil.which(command[0])
    if program is None:
        raise Failure("agent_not_found", f"エージェント {command[0]} が見つかりません。",
                      f"{command[0]} をインストールし、PATH から実行できるようにしてください。")
    args = [program, *command[1:]]
    if Path(command[0]).stem.lower() == "claude":
        if "--effort" not in command:
            args += ["--effort", "low"]
        args += ["--mcp-config", str(directory() / MCP_CONFIG), "--strict-mcp-config"]
    return args


# 状態（Electron の窓が読む：status.json・replied.json。置き場所は端末の出力の印で知らせる） ----------------------------
REPORT = r'''# ECOBuild GUI が置く：Claude Code の statusLine・フックが受け取った情報を、このフォルダに書き出す（標準ライブラリだけ）
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
kind = sys.argv[1] if len(sys.argv) > 1 else "statusline"
try:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
except Exception:
    data = {}
def write(name, value):
    path = os.path.join(here, name)
    try:
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)
    except OSError:
        pass
if kind == "replied":
    message = data.get("last_assistant_message")
    write("replied.json", {"at": time.time(), "message": message if isinstance(message, str) else None})
elif kind == "prompt":
    write("prompted.json", {"at": time.time()})
else:
    model = data.get("model") or {}
    window = data.get("context_window") or {}
    info = {"at": time.time(), "model": model.get("display_name") or model.get("id"),
            "context": window.get("used_percentage"), "limits": data.get("rate_limits"),
            "session": data.get("session_id"), "cwd": (data.get("workspace") or {}).get("current_dir") or data.get("cwd")}
    write("status.json", info)
    parts = [info["model"] or "Claude"]
    if info["context"] is not None:
        parts.append("ctx %d%%" % round(info["context"]))
    sys.stdout.buffer.write(" · ".join(parts).encode("utf-8"))
'''
VOICE = {"voice": {"enabled": True, "mode": "hold", "autoSubmit": False}, "promptSuggestionEnabled": False}


def status_folder() -> Path:
    """起動ごとの状態の置き場所（2つ動いても互いを消さない）。1日より古いものは片付ける。"""
    base = directory() / "status"
    base.mkdir(parents=True, exist_ok=True)
    for old in base.iterdir():
        try:
            if old.is_dir() and time.time() - old.stat().st_mtime > 86400:
                shutil.rmtree(old, ignore_errors=True)
        except OSError:
            pass
    folder = base / str(os.getpid())
    folder.mkdir(exist_ok=True)
    (folder / "report.py").write_text(REPORT, encoding="utf-8", newline="\n")
    return folder


def status_settings(folder: Path) -> Path:
    """一式の許可・フックに、状態を書き出す statusLine・フックと音声入力の設定を足したファイル（--settings に渡す）。"""
    try:
        settings = json.loads((directory() / SETTINGS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        settings = {}
    report = f'"{python()}" "{(folder / "report.py").as_posix()}"'
    settings.update(VOICE)
    try:
        language = json.loads((Path.home() / ".claude" / "settings.json").read_text(encoding="utf-8")).get("language")
    except (OSError, ValueError, AttributeError):
        language = None
    if isinstance(language, str) and language:
        settings["language"] = language   # 音声入力の言語：このPCの Claude の設定に合わせる
    settings["statusLine"] = {"type": "command", "command": f"{report} statusline", "padding": 0}
    hooks = settings.setdefault("hooks", {})
    hooks["Stop"] = [*hooks.get("Stop", []), {"hooks": [{"type": "command", "command": f"{report} replied"}]}]
    hooks["UserPromptSubmit"] = [*hooks.get("UserPromptSubmit", []), {"hooks": [{"type": "command", "command": f"{report} prompt"}]}]
    path = folder / "settings.json"
    path.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8", newline="\n")
    return path


# 起動・話しかける -------------------------------------------------------------------------------------------------
def run(command: tuple[str, ...] = DEFAULT_COMMAND) -> int:
    """この端末で動かして待つ（Electron の窓が、自分の端末の中で常駐させる）。終了コードを返す。"""
    folder = prepare()
    args = _command(command)
    if Path(args[0]).stem.lower() == "claude":
        status = status_folder()
        if sys.stdout.isatty():
            sys.stdout.write(STATUS_MARK.format(status.as_posix()))
            sys.stdout.flush()
        args += ["--settings", status_settings(status).as_posix()]
    try:
        return subprocess.run(args, cwd=folder).returncode
    except OSError as error:
        raise Failure("launch_failed", f"エージェントを起動できませんでした：{error}") from None
    except KeyboardInterrupt:
        return 130


def start(command: tuple[str, ...] = DEFAULT_COMMAND) -> dict:
    """新しい端末の画面で起動して、待たずに戻る。"""
    folder = prepare()
    args = _command(command)
    if Path(args[0]).stem.lower() == "claude":
        args += ["--settings", str(folder / SETTINGS)]
    try:
        if sys.platform == "win32":
            process = subprocess.Popen(args, cwd=folder, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            terminal = next((shutil.which(n) for n in (os.environ.get("TERMINAL"), "x-terminal-emulator") if n and shutil.which(n)), None)
            if terminal is None:
                raise Failure("no_terminal", "新しい画面を開く端末が見つかりません。",
                              "環境変数 TERMINAL に端末のコマンドを設定するか、--here でこの端末で動かしてください。")
            process = subprocess.Popen([terminal, "-e", *args], cwd=folder, start_new_session=True,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as error:
        raise Failure("launch_failed", f"エージェントを起動できませんでした：{error}") from None
    return {"pid": process.pid, "command": args, "directory": str(folder)}


def ask(text: str, *, session: str | None = None, command: tuple[str, ...] = DEFAULT_COMMAND,
        timeout: float | None = None) -> dict:
    """画面を開かずに1回話しかけて返答を待つ。{session, text, ok, actions:[{tool, command, ok, output}]}。"""
    if not text.strip():
        raise Failure("usage_error", "話しかける文が空です。", exit_code=2)
    folder = prepare()
    args = [*_command(command), "-p", "--output-format", "stream-json", "--verbose", "--settings", str(folder / SETTINGS)]
    if session:
        args += ["--resume", session]
    try:
        done = subprocess.run(args, cwd=folder, input=text, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Failure("timeout", f"オペレーターの返答が {timeout:g} 秒で終わりませんでした。") from None
    except OSError as error:
        raise Failure("launch_failed", f"エージェントを起動できませんでした：{error}") from None
    reply = parse(done.stdout)
    if reply is None:
        tail = (done.stderr or done.stdout).strip().splitlines()[-5:]
        raise Failure("ask_failed", "オペレーターから返答がありませんでした。" + ("\n" + "\n".join(tail) if tail else ""))
    return reply


def parse(output: str) -> dict | None:
    """claude -p の stream-json の出力を読む。終わりの印（result）がなければ None。"""
    session = None
    used: dict[str, dict] = {}
    texts: list[str] = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        session = event.get("session_id") or session
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if event.get("type") == "assistant" and isinstance(content, list):
            for block in filter(lambda b: isinstance(b, dict), content):
                if block.get("type") == "tool_use":
                    used[block.get("id", "")] = {"tool": block.get("name", ""), "ok": None, "output": "",
                                                 "command": describe(block.get("name", ""), block.get("input") or {})}
                elif block.get("type") == "text":
                    texts.append(block.get("text", ""))
        elif event.get("type") == "user" and isinstance(content, list):
            for block in filter(lambda b: isinstance(b, dict), content):
                if block.get("type") == "tool_result" and block.get("tool_use_id") in used:
                    used[block["tool_use_id"]].update(ok=not block.get("is_error"), output=_text(block.get("content")))
        elif event.get("type") == "result":
            text = event.get("result") if isinstance(event.get("result"), str) else (texts[-1] if texts else "")
            return {"session": event.get("session_id") or session, "text": text, "ok": not event.get("is_error"),
                    "actions": list(used.values())}
    return None


def describe(tool: str, given: dict) -> str:
    """使った道具を1行で（会話の窓の「実行したコマンド」に出す）。"""
    name = tool.split("__")[-1]
    if name == "ecobuild_read":
        where = f"-C {given['dir']} " if given.get("dir") else ""
        return f"{PROGRAM} {where}{' '.join(str(a) for a in given.get('args') or [])}".strip()
    if name.startswith("gui_"):
        options = " ".join(f"--{k} {v}" for k, v in given.items())
        return f"{PROGRAM} gui {name[4:]} {options}".strip()
    return str(given.get("command") or name)


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


# 話しかけられるたびに渡す文脈（UserPromptSubmit のフック） -----------------------------------------------------------
def context() -> str:
    """今のモジュールと中の作業空間の一覧（名前・場所・ブランチ）。場所を調べる道具を使わずに、すぐ操作できるように。"""
    document = ecobuild(["workspace", "list"], timeout=30)
    result = document.get("result") if document.get("ok") else None
    modules = [e for e in (result.get("modules") or []) if isinstance(e, dict) and e.get("exists", True)] \
        if isinstance(result, dict) else []
    if not modules:
        return ""
    lines = ["今のモジュールと作業空間（ECOBuild GUI が足した情報。場所はこれを使い、ここで分からないときだけ workspace list）："]
    for e in modules:
        path = str(e.get("path") or "")
        name = (e.get("repository") or "").split("/")[-1] or path.replace("\\", "/").rstrip("/").split("/")[-1]
        lines.append(f"- {name}：{path}（{_where(e)}{'・' + e['type'] if e.get('type') else ''}）")
        lines += [f"  - 作業空間 {w.get('name')}：{w.get('path')}（{_where(w)}）"
                  for w in e.get("workspaces") or [] if isinstance(w, dict)]
    return "\n".join(lines)


def _where(e: dict) -> str:
    return (e.get("branch") or "ブランチなし") + (f"＝タスク #{e['task']}" if e.get("task") is not None else "")
