"""ecobuild gui：ECOBuild GUI を、外（端末・AIエージェント）から操作する（ecobuild の外部サブコマンド。ecobuild-gui）。

画面のボタンと同じ「GUIの操作」（actions.py）を、動いているGUIのサーバーに頼む。人が画面を見ていれば、操作はそこに
反映される（エージェントが実行したこと・開いた画面）。GUIが動いていなければ起動する。

GUI は2つある（今までの GUI と、GUIFrameWork の上の新しい GUI：gui/eco_gui）。どちらに頼むかの決まり（target）：
  1. 環境変数 ECOBUILD_GUI_TARGET（next・classic）があれば、それ。
  2. 新しい GUI の中から頼まれた（新しい GUI の画面が実行したコマンド・そこから話しかけたオペレーター）なら、新しい GUI。
  3. ほか（端末・今までの GUI のオペレーター）は、動いている方。両方動いていれば、新しい GUI（主にする方）。
  4. どちらも動いていなければ、新しい GUI を起動する（準備されていなければ、今までの GUI）。
新しい GUI には、表示の CLI（next_gui.py）で頼む：open・windows・notify・folder・vs と、新しい GUI だけの
screens（画面の一覧）・tree（今の表示を読む）・emit（人の代わりに入力を出す）。エージェントの窓の操作は、今までの GUI だけ。

  ecobuild gui                         ハブを開く
  ecobuild gui task start 12           ecobuild のコマンドを、GUIを通して実行（-C <場所> で場所を指定）
  ecobuild gui open [モジュール] [--page …] [--tab …] [--task N] [--command "task start"]
  ecobuild gui folder <場所> [--path …] / vs <場所> [--path …] / notify "…"
  ecobuild gui windows / activity     開いている窓と表示しているもの・最近の操作（エージェント向け）
  ecobuild gui screens / tree [--window W] / emit <窓>/<部品> <出力> [--payload 名前=値 …]
                                       新しい GUI だけ：画面の一覧／窓の今の表示を読む／人の代わりに入力を出す
  ecobuild gui actions [--json]        GUIの操作の一覧（--help --json と同じ。頼み先の GUI のもの）
  ecobuild gui mcp [--operator]        MCP サーバー（標準入出力）。エージェントのツールとして登録する
                                       （--operator：オペレーター用。GUI の操作と、見るだけの ecobuild のコマンドだけ）
  ecobuild gui operator [--here] [--agent "claude …"]
                                       オペレーター（GUI の案内・操作係のエージェント）を新しい画面で起動
                                       （--here：この端末で動かして待つ。Electron の窓が裏で常駐させる）
  ecobuild gui ask "…" [--session S | --continue]
                                       オペレーターに画面を開かずに話しかけ、返答を待つ（文は省くか - で標準入力）
                                       （--continue：このPCの会話の記録の続きとして話し、発言と返答を記録に足す）
  ecobuild gui conversation            会話の記録（発言・返答・実行したコマンド）と、今の状態（待機中・考え中）
  ecobuild gui conversation-new        会話の記録を空にする（次の ask --continue から新しい会話）
  ecobuild gui login / scope / pick-folder / shortcut / quit / update
                                       新しい GUI の画面が呼ぶ、この PC の窓まわり（next_commands.py）

結果は --json で ecobuild と同じ形の JSON（ok・result・error）。終了コードも ecobuild と同じ（0 成功・1 失敗・2 誤り）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import actions  # noqa: E402
import next_commands  # noqa: E402
import next_gui  # noqa: E402
import operator_kit  # noqa: E402
from operator_kit import Failure  # noqa: E402,F401（誤りは GUI の口で共通）

HERE = Path(__file__).resolve().parent
VERSION = "0.1.0"


# The running GUI server ------------------------------------------------------------------------------------------
def _home() -> Path:
    import app       # gui_home（GUIの設定の場所）はサーバーと同じ決め方で
    return app.gui_home()


def _state() -> dict | None:
    try:
        return json.loads((_home() / "server.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _post(state: dict, api: str, body: dict, timeout: float = 3600) -> object:
    request = urllib.request.Request(f"http://127.0.0.1:{state['port']}/api/{api}", data=json.dumps(body).encode("utf-8"),
                                     method="POST", headers={"Content-Type": "application/json", "X-ECOBuild-Token": state["token"]})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read())
    if data.get("error"):
        raise Failure("gui_error", data["error"])
    return data.get("value")


def _alive(state: dict | None) -> bool:
    if not state:
        return False
    try:
        _post(state, "ping", {}, timeout=2)
        return True
    except (OSError, ValueError, Failure):
        return False


def server(start: bool = True) -> dict:
    """動いているGUIのサーバー（場所と合言葉）。なければ起動して待つ（窓も開く：人が見られるように）。"""
    state = _state()
    if _alive(state):
        return state
    if not start:
        raise Failure("gui_not_running", "ECOBuild GUI が動いていません。", "ecobuild gui で起動できます。")
    old = (state or {}).get("token")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen([sys.executable, str(HERE / "app.py")], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        state = _state()
        if state and state.get("token") != old and _alive(state):
            return state
        time.sleep(0.3)
    raise Failure("gui_not_started", "ECOBuild GUI を起動できませんでした。", f"記録：{_home() / 'gui.log'}")


_decided: list = []   # [決めた時刻, 頼み先]。1つの頼みの中で、動いているかを何度も調べない（数秒だけ覚える）


def target() -> str:
    """どちらの GUI に頼むか（next：新しい GUI、classic：今までの GUI）。決まりは、このファイルの先頭。"""
    chosen = next_gui.chosen()
    if chosen:
        return chosen
    if _decided and time.monotonic() - _decided[0] < 3:
        return _decided[1]
    if next_gui.running():
        where = next_gui.NEXT
    elif _alive(_state()) or next_gui.python() is None:   # 今までの GUI だけが動いている・新しい GUI が準備されていない
        where = next_gui.CLASSIC
    else:
        where = next_gui.NEXT   # どちらも動いていない：新しい GUI を起動する（next_gui.act）
    _decided[:] = [time.monotonic(), where]
    return where


def table(where: str | None = None) -> dict[str, actions.Action]:
    """頼み先の GUI の操作の一覧。"""
    return next_gui.ACTIONS if (where or target()) == next_gui.NEXT else actions.ACTIONS


REQUESTER: str | None = None   # 新しい GUI の窓の枠に出す依頼元（MCP なら「オペレーター」「エージェント」）


def _ecobuild(args: list[str], directory: str | None = None, stdin: str | None = None) -> dict:
    """ecobuild [-C 場所] <引数> --json の文書（新しい GUI での run。画面も同じ ecobuild を呼ぶ）。"""
    command = [operator_kit.PROGRAM, *(["-C", directory] if directory else []), *args, "--json"]
    try:
        done = subprocess.run(command, input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL, capture_output=True,
                              encoding="utf-8", errors="replace")
        lines = done.stdout.strip().splitlines()
        return json.loads(lines[-1]) if lines else {"ok": False, "error": {"code": "no_output", "message": (done.stderr or "").strip()}}
    except (OSError, ValueError) as error:
        return {"ok": False, "error": {"code": "gui_error", "message": f"ecobuild を実行できませんでした：{error}"}}


def act(name: str, params: dict) -> object:
    """GUIの操作を頼む（画面のボタンと同じ道）。頼み先は target()。"""
    if target() == next_gui.NEXT:
        try:
            return next_gui.act(name, params, ecobuild=_ecobuild, by=REQUESTER)
        except ValueError as error:
            raise Failure("usage_error", str(error), "ecobuild gui actions で一覧を確かめてください。", 2) from None
        except next_gui.Refused as refused:
            hint = "ECOBuild GUI を起動してください。" if refused.code == "no_display" and not refused.hint else refused.hint
            raise Failure(refused.code, refused.message, hint) from None
    try:
        clean = actions.check(name, params)
    except ValueError as error:
        raise Failure("usage_error", str(error), "ecobuild gui actions で一覧を確かめてください。", 2) from None
    try:
        return _post(server(), "action", {"name": name, "params": clean, "origin": ""})
    except urllib.error.URLError as error:
        raise Failure("gui_error", f"ECOBuild GUI に頼めませんでした：{error.reason}") from None


# Command line ----------------------------------------------------------------------------------------------------
def _parse(name: str, words: list[str], known_actions: dict[str, actions.Action] | None = None) -> dict:
    """ecobuild gui <操作> の残り：位置引数は必須の引数に順に、--名前 値 はその引数に（boolean は値なし。並びは何度でも）。"""
    known = {p.name: p for p in (actions.ACTIONS if known_actions is None else known_actions)[name].params}
    positional = [p for p in known.values() if p.required and p.kind != "array"]
    values: dict = {}
    i = 0
    while i < len(words):
        word = words[i]
        if word.startswith("--"):
            key = word[2:].replace("-", "_")
            if key not in known:
                raise Failure("usage_error", f"{name} に --{word[2:]} はありません（{'・'.join('--' + k for k in known) or 'なし'}）。",
                              exit_code=2)
            if known[key].kind == "boolean":
                values[key] = True
            else:
                i += 1
                if i >= len(words):
                    raise Failure("usage_error", f"--{key} に値を指定してください。", exit_code=2)
                if known[key].kind == "array":
                    values.setdefault(key, []).append(words[i])
                else:
                    values[key] = words[i]
        elif positional:
            values[positional.pop(0).name] = word
        elif name == "open" and "module" not in values:
            values["module"] = word
        else:
            raise Failure("usage_error", f"{name} の引数が多すぎます：{word}", exit_code=2)
        i += 1
    return values


def _print(document: dict, json_output: bool) -> int:
    if json_output:
        print(json.dumps(document, ensure_ascii=False))
    elif document.get("ok"):
        result = document.get("result")
        if result not in (None, {}, []):
            print(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2))
        for notice in document.get("notices") or []:
            print(f"お知らせ：{notice}", file=sys.stderr)
    else:
        error = document.get("error") or {}
        print(f"エラー：{error.get('message', '')}", file=sys.stderr)
        if error.get("hint"):
            print(f"ヒント：{error['hint']}", file=sys.stderr)
    return 0 if document.get("ok") else (document.get("exit_code") or 1)


# オペレーターとの会話のコマンド（ecobuild --help --json のコマンドと同じ形。画面はこの形から呼ぶ引数を知る）
COMMANDS = [
    {"name": "ask", "path": "gui ask", "runnable": True, "effect": "change",
     "summary": "オペレーターに画面を開かずに話しかけ、返答を待ちます。",
     "arguments": [{"param": "text", "type": "str", "required": False, "multiple": False,
                    "help": "話しかける文（省くか - で標準入力）"}],
     "options": [{"param": "session", "names": ["--session"], "type": "str", "help": "続ける会話（前の返答の session）"},
                 {"param": "continue", "names": ["--continue"], "type": "bool",
                  "help": "このPCの会話の記録の続きとして話し、発言と返答を記録に足す"},
                 {"param": "agent", "names": ["--agent"], "type": "str", "help": "エージェントのコマンド（既定は claude）"}]},
    {"name": "conversation", "path": "gui conversation", "runnable": True, "effect": "read",
     "summary": "オペレーターとの会話の記録と、今の状態（待機中・考え中）を表示します。", "arguments": [], "options": []},
    {"name": "conversation-new", "path": "gui conversation-new", "runnable": True, "effect": "change",
     "summary": "オペレーターとの会話の記録を空にします（次の ask --continue から新しい会話）。", "arguments": [], "options": []},
    *next_commands.COMMANDS,   # 新しい GUI の画面が呼ぶ、この PC の窓まわり（ログインの端末・フォルダを選ぶ・ショートカット・終了・更新）
]


def help_document(where: str | None = None) -> dict:
    """ecobuild gui --help --json の result。commands は、ecobuild の一覧（extensions）に入る形（頼み先によらず同じ）。
    actions は、頼み先（where。省くと今までの GUI）の GUIの操作。"""
    known = table(where or next_gui.CLASSIC)
    return {"name": "gui", "summary": "ECOBuild GUI を外（端末・AIエージェント）から操作します。",
            "help": (__doc__ or "").strip(), "actions": [a.describe() for a in known.values()], "commands": COMMANDS,
            "examples": [{"say": say, "do": do} for say, do in operator_kit.spoken_examples(known)]}


def main(argv: list[str] | None = None) -> int:
    words = list(sys.argv[1:] if argv is None else argv)
    json_output = "--json" in words
    if not words or words == ["--json"]:
        return run_action("open", {}, json_output)
    if words[0] in ("--help", "-h", "help", "actions"):
        # --help は ecobuild の一覧からも呼ばれる（速く答える：どちらが動いているかは調べない）。actions は頼み先の GUI のもの
        where = target() if words[0] == "actions" else next_gui.chosen()
        if json_output:
            print(json.dumps({"ok": True, "command": "gui actions", "result": help_document(where), "error": None}, ensure_ascii=False))
        elif words[0] == "actions":
            for a in table(where).values():
                params = " ".join(("<" if p.required else "[--") + p.name + (">" if p.required else "]") for p in a.params)
                print(f"{a.name:9} {params}\n          {a.summary}")
        else:
            print((__doc__ or "").strip())
        return 0
    if words[0] == "mcp":
        return mcp(operator="--operator" in words[1:])
    if words[0] == "operator" and not _operator_action(words[1:]):
        return operator_command([w for w in words[1:] if w != "--json"], json_output)
    if words[0] == "ask":
        return ask_command([w for w in words[1:] if w != "--json"], json_output)
    if words[0] in ("conversation", "conversation-new"):
        return conversation_command(words[0], [w for w in words[1:] if w != "--json"], json_output)
    if words[0] in next_commands.NAMES:
        name = words[0]
        try:
            result = next_commands.run(name, [w for w in words[1:] if w != "--json"])
            document = {"ok": True, "command": f"gui {name}", "result": result, "error": None}
        except Failure as failure:
            document = _failed(f"gui {name}", failure)
        return _print(document, json_output)
    if words[0] == "operator-context":   # オペレーターのフック（話しかけられるたびに今の作業空間を渡す）
        text = operator_kit.context()
        if text:
            print(text)
        return 0
    if (words[0] in actions.ACTIONS or words[0] in next_gui.ACTIONS) and words[0] != "run":
        name = words[0]
        where = target()
        if name not in table(where):   # 頼み先の GUI にない操作：その GUI が、ない理由と代わりを答える
            return run_action(name, {}, json_output)
        try:
            params = _parse(name, [w for w in words[1:] if w != "--json"], table(where))
        except Failure as failure:
            return _print({"ok": False, "error": {"code": failure.code, "message": failure.message, "hint": failure.hint},
                           "exit_code": failure.exit_code}, json_output)
        if name in ("folder", "vs") and "dir" in params:
            params["dir"] = str(Path(params["dir"]).resolve())
        return run_action(name, params, json_output)
    # Anything else is an ecobuild command, run through the GUI (-C <場所> as ecobuild).
    if words[0] == "run":
        words = words[1:]
    directory = str(Path.cwd())
    while words[:1] and words[0] in ("-C", "--directory"):
        if len(words) < 2:
            return _print({"ok": False, "error": {"code": "usage_error", "message": "-C にはパスを指定してください。"},
                           "exit_code": 2}, json_output)
        directory = str(Path(words[1]).resolve())
        words = words[2:]
    args = [w for w in words if w != "--json"]
    try:
        document = act("run", {"args": args, "dir": directory})
    except Failure as failure:
        document = {"ok": False, "error": {"code": failure.code, "message": failure.message, "hint": failure.hint},
                    "exit_code": failure.exit_code}
    return _print(document, json_output)


def _operator_action(words: list[str]) -> bool:
    """gui operator が、GUIの操作 operator（タブで開く・裏に戻す：--state show／hide）か。"""
    return "--state" in words or any(w in ("show", "hide") for w in words)


def _options(words: list[str], known: dict[str, bool]) -> tuple[dict, list[str]]:
    """--名前 値（known の値が True なら値なし）と、残りの言葉。"""
    values, rest, i = {}, [], 0
    while i < len(words):
        word = words[i]
        key = word[2:] if word.startswith("--") else None
        if key in known:
            if known[key]:
                values[key] = True
            elif i + 1 < len(words):
                values[key] = words[i + 1]
                i += 1
            else:
                raise Failure("usage_error", f"--{key} に値を指定してください。", exit_code=2)
        elif key is not None:
            raise Failure("usage_error", f"--{key} はありません（{'・'.join('--' + k for k in known)}）。", exit_code=2)
        else:
            rest.append(word)
        i += 1
    return values, rest


def _failed(command: str, failure: Failure) -> dict:
    return {"ok": False, "command": command, "result": None,
            "error": {"code": failure.code, "message": failure.message, "hint": failure.hint}, "exit_code": failure.exit_code}


def operator_command(words: list[str], json_output: bool) -> int:
    """ecobuild gui operator [--here] [--agent "claude …"]：オペレーターを起動する。"""
    try:
        values, rest = _options(words, {"here": True, "agent": False})
        if rest:
            raise Failure("usage_error", f"operator の引数が多すぎます：{rest[0]}", exit_code=2)
        command = tuple(str(values.get("agent", "")).split()) or operator_kit.DEFAULT_COMMAND
        where = {"gui": next_gui.NEXT} if target() == next_gui.NEXT else {}   # GUI の操作の頼み先（今までの GUI なら今までどおり）
        if values.get("here"):
            return operator_kit.run(command, **where)
        started = operator_kit.start(command, **where)
    except Failure as failure:
        return _print(_failed("gui operator", failure), json_output)
    if not json_output:
        print(f"オペレーターを起動しました：{' '.join(started['command'])}（{started['directory']}）")
        return 0
    return _print({"ok": True, "command": "gui operator", "result": started, "error": None}, json_output)


def ask_command(words: list[str], json_output: bool) -> int:
    """ecobuild gui ask "…" [--session S | --continue] [--agent "claude …"]：オペレーターに1回話しかける。

    文は省くか - で標準入力。--json のときは、途中で使い始めた道具を、標準エラーに1行ずつ出す（ecobuild のイベントと同じ形の
    kind: output。画面の「実行中：…」）。
    """
    def started(name: str) -> None:
        if json_output:
            print(json.dumps({"kind": "output", "text": name, "stream": "stdout", "source": "tool"}, ensure_ascii=False),
                  file=sys.stderr, flush=True)

    try:
        cut = words.index("--") if "--" in words else len(words)   # 「--」の後ろは、- で始まっても文
        values, rest = _options(words[:cut], {"session": False, "agent": False, "continue": True})
        rest += words[cut + 1:]
        if values.get("continue") and values.get("session"):
            raise Failure("usage_error", "--continue と --session は一緒に指定できません。", exit_code=2)
        message = "" if rest == ["-"] else " ".join(rest)
        message = message or (sys.stdin.read() if not sys.stdin.isatty() else "")
        command = tuple(str(values.get("agent", "")).split()) or operator_kit.DEFAULT_COMMAND
        where = target()   # オペレーターの GUI の操作の頼み先（新しい GUI から話しかけたら、新しい GUI）
        if values.get("continue"):
            reply = operator_kit.converse(message, command=command, on_action=started, gui=where)
        else:
            reply = operator_kit.ask(message, session=values.get("session") or None, command=command, on_action=started, gui=where)
    except Failure as failure:
        return _print(_failed("gui ask", failure), json_output)
    if not json_output:
        done = [f"  $ {a['command']}" + ("（失敗）" if a["ok"] is False else "") for a in reply["actions"] if a["command"]]
        print("\n".join([*done, reply["text"], f"（会話：{reply['session']}）" if reply["session"] else ""]).strip())
        return 0
    return _print({"ok": True, "command": "gui ask", "result": reply, "error": None}, json_output)


def conversation_command(name: str, words: list[str], json_output: bool) -> int:
    """ecobuild gui conversation：会話の記録と今の状態。ecobuild gui conversation-new：記録を空にする。"""
    try:
        if words:
            raise Failure("usage_error", f"{name} に引数はありません：{words[0]}", exit_code=2)
        found = operator_kit.forget() if name == "conversation-new" else operator_kit.conversation()
    except Failure as failure:
        return _print(_failed(f"gui {name}", failure), json_output)
    if json_output:
        return _print({"ok": True, "command": f"gui {name}", "result": found, "error": None}, json_output)
    if name == "conversation-new":
        print("会話の記録を空にしました。")
        return 0
    for message in found["messages"]:
        who = "自分" if message.get("role") == "user" else "オペレーター" + ("（失敗）" if message.get("ok") is False else "")
        print(f"{who}：{message.get('text') or ''}")
        for action in message.get("actions") or []:
            print(f"  $ {action.get('command')}" + ("（失敗）" if action.get("ok") is False else ""))
    print("（起動中…）" if found["state"] == "starting"
          else "（考え中…" + (f" 実行中：{found['doing']}" if found.get("doing") else "") + "）" if found["state"] == "thinking"
          else "（会話はまだありません）" if not found["messages"] else "（待機中）")
    return 0


def run_action(name: str, params: dict, json_output: bool) -> int:
    try:
        result = act(name, params)
        document = {"ok": True, "command": f"gui {name}", "result": result, "error": None}
    except Failure as failure:
        document = {"ok": False, "command": f"gui {name}", "result": None,
                    "error": {"code": failure.code, "message": failure.message, "hint": failure.hint}, "exit_code": failure.exit_code}
    return _print(document, json_output)


# MCP（Model Context Protocol）：標準入出力の JSON-RPC。ツールは GUIの操作と、ecobuild のコマンドの一覧 ------------
MCP_PROTOCOL = "2025-06-18"
TOOL_PREFIX = "gui_"
INSTRUCTIONS = ("ECOBuild GUI を、人が画面を見ている前で操作するためのツールです。ecobuild ツールで ECOBuild のコマンドを実行し"
                "（使い方は ecobuild_commands）、gui_open で画面を見せ、gui_windows・gui_activity で今の様子を確かめます。"
                "確認が要るコマンドは、人に確かめてから --yes を付けます。")
OPERATOR_INSTRUCTIONS = ("ECOBuild GUI を、人が画面を見ている前で案内・操作するためのツールです（オペレーター用）。gui_open で画面を見せ、"
                         "gui_windows・gui_activity で今の様子を確かめ、ecobuild_read で見るだけのコマンドを実行します"
                         "（使い方は ecobuild_commands）。ECOBuild を変える操作はできません。")


def mcp_tools(operator: bool = False, where: str | None = None) -> list[dict]:
    """MCP のツール：頼み先の GUI（where。省くと target()）の GUIの操作と、ecobuild のコマンドの一覧。
    operator：オペレーター用（何でも実行できる ecobuild・入力を出す emit・agent-send を外し、見るだけの ecobuild_read を足す）。"""
    def schema(action: actions.Action) -> dict:
        properties = {}
        for p in action.params:
            kind = {"string": "string", "integer": "integer", "boolean": "boolean", "array": "array"}[p.kind]
            prop = {"type": kind, "description": p.help}
            if p.kind == "array":
                prop["items"] = {"type": "string"}
            if p.choices:
                prop["enum"] = list(p.choices)
            properties[p.name] = prop
        return {"type": "object", "properties": properties, "required": [p.name for p in action.params if p.required]}

    tools = []
    for a in table(where).values():
        if operator and a.name in operator_kit.hidden_actions():
            continue
        name = "ecobuild" if a.name == "run" else TOOL_PREFIX + a.name
        description = a.summary + (" " + a.help if a.help else "")
        if a.name == "run":
            description += " 人がGUIを開いていれば、実行したことがそこに表示されます。"
        tools.append({"name": name, "description": description, "inputSchema": schema(a)})
    tools.append({"name": "ecobuild_commands",
                  "description": "ECOBuild のコマンドの一覧（説明・引数・オプション）。path を指定するとそのコマンドだけ（例：\"task start\"）。"
                                 "型ごとのコマンド（build・test 等）は型ごとに分かれています。型のコマンドを path で見るときは、"
                                 "dir にその型のモジュール・作業空間を指定します。",
                  "inputSchema": {"type": "object", "properties": {
                      "path": {"type": "string", "description": "コマンド（省略で全部）"},
                      "dir": {"type": "string", "description": "読む場所（モジュール・作業空間のフォルダ。省略時はこのフォルダ）"}}}})
    if operator:
        tools.append({"name": "ecobuild_read",
                      "description": "見るだけ（重さが read）の ECOBuild のコマンドを、GUIを通して実行します（例：args に [\"task\", \"list\"]）。"
                                     "変えるコマンドは断られます。",
                      "inputSchema": {"type": "object", "properties": {
                          "args": {"type": "array", "items": {"type": "string"}, "description": "ecobuild の引数（-C は使わず dir に）"},
                          "dir": {"type": "string", "description": "実行する場所（モジュール・作業空間のフォルダ。省略時はこのフォルダ）"}},
                          "required": ["args"]}})
    return tools


def mcp_call(name: str, arguments: dict, operator: bool = False) -> tuple[object, bool]:
    if name == "ecobuild_commands":
        # 型のコマンド（build・deps 等）は、その型のモジュールの中で読むときだけ重なる（外では使えない誤り）
        where = arguments.get("dir") or ""
        command = ["ecobuild", *(["-C", where] if where else []), *arguments.get("path", "").split(), "--help", "--json"]
        completed = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
        document = json.loads(completed.stdout.strip().splitlines()[-1]) if completed.stdout.strip() else {"ok": False}
        return document.get("result") if document.get("ok") else document, not document.get("ok")
    if operator and name == "ecobuild_read":
        args = [str(a) for a in arguments.get("args") or [] if str(a) != "--json"]
        operator_kit.read_command(args, operator_kit.catalog())
        where = arguments.get("dir") or str(Path.cwd())
        if target() == next_gui.NEXT:   # 読むだけなので、窓に読み直しを頼まない（新しい GUI の画面も、同じ ecobuild を呼ぶ）
            result = _ecobuild(args, where)
        else:
            result = act("run", {"args": args, "dir": where})
        return result, not (isinstance(result, dict) and result.get("ok"))
    action = "run" if name == "ecobuild" else name[len(TOOL_PREFIX):] if name.startswith(TOOL_PREFIX) else ""
    if not (action in actions.ACTIONS or action in next_gui.ACTIONS) or (operator and action in operator_kit.hidden_actions()):
        raise Failure("usage_error", f"ツール {name} はありません。", exit_code=2)
    params = dict(arguments)
    if action == "run" and not params.get("dir"):
        params["dir"] = str(Path.cwd())
    result = act(action, params)   # 頼み先の GUI にない操作は、その GUI が、ない理由と代わりを答える
    if action == "run":
        return result, not (isinstance(result, dict) and result.get("ok"))
    return result, False


def mcp(operator: bool = False) -> int:
    global REQUESTER
    REQUESTER = "オペレーター" if operator else "エージェント"

    def send(message: dict) -> None:
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except ValueError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        method, ident = request.get("method"), request.get("id")
        if ident is None:          # notifications (initialized 等)
            continue
        try:
            if method == "initialize":
                result = {"protocolVersion": (request.get("params") or {}).get("protocolVersion", MCP_PROTOCOL),
                          "capabilities": {"tools": {}},
                          "serverInfo": {"name": "ecobuild-gui", "version": VERSION},
                          "instructions": OPERATOR_INSTRUCTIONS if operator else INSTRUCTIONS}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": mcp_tools(operator)}
            elif method == "tools/call":
                params = request.get("params") or {}
                value, is_error = mcp_call(params.get("name", ""), params.get("arguments") or {}, operator)
                result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2)}], "isError": is_error}
            else:
                send({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"method not found: {method}"}})
                continue
            send({"jsonrpc": "2.0", "id": ident, "result": result})
        except Failure as failure:
            send({"jsonrpc": "2.0", "id": ident, "result": {"content": [{"type": "text", "text": failure.message +
                                                                           (f"\n{failure.hint}" if failure.hint else "")}],
                                                           "isError": True}})
    return 0


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
