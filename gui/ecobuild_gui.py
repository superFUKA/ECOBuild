"""ecobuild gui：ECOBuild GUI を、外（端末・AIエージェント）から操作する（ecobuild の外部サブコマンド。ecobuild-gui）。

画面のボタンと同じ「GUIの操作」（actions.py）を、動いているGUIのサーバーに頼む。人が画面を見ていれば、操作はそこに
反映される（エージェントが実行したこと・開いた画面）。GUIが動いていなければ起動する。

  ecobuild gui                         ハブを開く
  ecobuild gui task start 12           ecobuild のコマンドを、GUIを通して実行（-C <場所> で場所を指定）
  ecobuild gui open [モジュール] [--page …] [--tab …] [--task N] [--command "task start"]
  ecobuild gui folder <場所> [--path …] / vs <場所> [--path …] / notify "…"
  ecobuild gui windows / activity     開いている窓と表示しているもの・最近の操作（エージェント向け）
  ecobuild gui actions [--json]        GUIの操作の一覧（--help --json と同じ）
  ecobuild gui mcp [--operator]        MCP サーバー（標準入出力）。エージェントのツールとして登録する
                                       （--operator：オペレーター用。GUI の操作と、見るだけの ecobuild のコマンドだけ）
  ecobuild gui operator [--here] [--agent "claude …"]
                                       オペレーター（GUI の案内・操作係のエージェント）を新しい画面で起動
                                       （--here：この端末で動かして待つ。Electron の窓が裏で常駐させる）
  ecobuild gui ask "…" [--session S]   オペレーターに画面を開かずに話しかけ、返答を待つ（文は省くと標準入力）

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


def act(name: str, params: dict) -> object:
    """GUIの操作を頼む（画面のボタンと同じ道）。"""
    try:
        clean = actions.check(name, params)
    except ValueError as error:
        raise Failure("usage_error", str(error), "ecobuild gui actions で一覧を確かめてください。", 2) from None
    try:
        return _post(server(), "action", {"name": name, "params": clean, "origin": ""})
    except urllib.error.URLError as error:
        raise Failure("gui_error", f"ECOBuild GUI に頼めませんでした：{error.reason}") from None


# Command line ----------------------------------------------------------------------------------------------------
OPTIONS = {   # 操作の引数（--名前 値。boolean は値なし）
    a.name: {p.name: p for p in a.params} for a in actions.ACTIONS.values()
}


def _parse(name: str, words: list[str]) -> dict:
    """ecobuild gui <操作> の残り：位置引数は必須の引数に順に、--名前 値 はその引数に。"""
    known = OPTIONS[name]
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


def help_document() -> dict:
    return {"name": "gui", "summary": "ECOBuild GUI を外（端末・AIエージェント）から操作します。",
            "help": (__doc__ or "").strip(), "actions": actions.catalog(),
            "examples": [{"say": say, "do": do} for say, do in actions.EXAMPLES]}


def main(argv: list[str] | None = None) -> int:
    words = list(sys.argv[1:] if argv is None else argv)
    json_output = "--json" in words
    if not words or words == ["--json"]:
        return run_action("open", {}, json_output)
    if words[0] in ("--help", "-h", "help", "actions"):
        if json_output:
            print(json.dumps({"ok": True, "command": "gui actions", "result": help_document(), "error": None}, ensure_ascii=False))
        elif words[0] == "actions":
            for a in actions.ACTIONS.values():
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
    if words[0] == "operator-context":   # オペレーターのフック（話しかけられるたびに今の作業空間を渡す）
        text = operator_kit.context()
        if text:
            print(text)
        return 0
    if words[0] in actions.ACTIONS and words[0] != "run":
        name = words[0]
        try:
            params = _parse(name, [w for w in words[1:] if w != "--json"])
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
        if values.get("here"):
            return operator_kit.run(command)
        started = operator_kit.start(command)
    except Failure as failure:
        return _print(_failed("gui operator", failure), json_output)
    if not json_output:
        print(f"オペレーターを起動しました：{' '.join(started['command'])}（{started['directory']}）")
        return 0
    return _print({"ok": True, "command": "gui operator", "result": started, "error": None}, json_output)


def ask_command(words: list[str], json_output: bool) -> int:
    """ecobuild gui ask "…" [--session S] [--agent "claude …"]：オペレーターに1回話しかける（文は省くと標準入力）。"""
    try:
        values, rest = _options(words, {"session": False, "agent": False})
        message = " ".join(rest) or (sys.stdin.read() if not sys.stdin.isatty() else "")
        command = tuple(str(values.get("agent", "")).split()) or operator_kit.DEFAULT_COMMAND
        reply = operator_kit.ask(message, session=values.get("session") or None, command=command)
    except Failure as failure:
        return _print(_failed("gui ask", failure), json_output)
    if not json_output:
        done = [f"  $ {a['command']}" + ("（失敗）" if a["ok"] is False else "") for a in reply["actions"] if a["command"]]
        print("\n".join([*done, reply["text"], f"（会話：{reply['session']}）" if reply["session"] else ""]).strip())
        return 0
    return _print({"ok": True, "command": "gui ask", "result": reply, "error": None}, json_output)


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


def mcp_tools(operator: bool = False) -> list[dict]:
    """MCP のツール。operator：オペレーター用（何でも実行できる ecobuild と agent-send を外し、見るだけの ecobuild_read を足す）。"""
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
    for a in actions.ACTIONS.values():
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
        result = act("run", {"args": args, "dir": arguments.get("dir") or str(Path.cwd())})
        return result, not (isinstance(result, dict) and result.get("ok"))
    action = "run" if name == "ecobuild" else name[len(TOOL_PREFIX):] if name.startswith(TOOL_PREFIX) else ""
    if action not in actions.ACTIONS or (operator and action in operator_kit.hidden_actions()):
        raise Failure("usage_error", f"ツール {name} はありません。", exit_code=2)
    params = dict(arguments)
    if action == "run" and not params.get("dir"):
        params["dir"] = str(Path.cwd())
    result = act(action, params)
    if action == "run":
        return result, not (isinstance(result, dict) and result.get("ok"))
    return result, False


def mcp(operator: bool = False) -> int:
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
