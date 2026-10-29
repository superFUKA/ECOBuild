"""エージェント専用の MCP サーバー（ecobuild agent mcp）：作業空間のエージェントに、許したツールだけを渡す。

CLI をデータとして使う（この拡張は CLI を import しない）。
- 起動したら ecobuild -C <作業空間> --help --json を1回読み、共通のコマンドと、その作業空間の型のコマンドのうち
  「エージェントに許す」の印（agent：read・change・owner）の付いたものをツールにする。
- ツールの名前は道筋を _ でつないだもの（task status → task_status）。入力の形は引数・オプション（param の名前）から作る。
  json・yes と、作業空間の外へ出るもの（-C）は入力に入れない（作業空間はサーバーの側で固定する）。
- 呼ばれたら ecobuild -C <作業空間> <道筋> <引数> --json を実行し、その JSON の文書（ok・result・error 等）をそのまま返す。
  確認のオプション（--yes）があるコマンドは、いつも --yes を付ける（登録で許したことを同意とみなす）。
- 渡すのは、登録の tools で許したもの（allows）。手伝い（helper）には owner の印のもの（ブランチを変える操作）を渡さない。
- ほかのツール（子を扱うもの等）は register_provider で足す。足したツールも登録の tools で絞る。
呼び手は MCP の引数で名乗らせない：起動のときに固定した Context（agent_id 等）で決まる。
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, TextIO

from ecoagent.mcp import Server, Tool, ToolError

OWNER, HELPER = "owner", "helper"
KINDS = (OWNER, HELPER)        # タスクの持ち主・手伝い（同じ作業空間で、コミットしない）
MARKS = ("read", "change", "owner")
HIDDEN_PARAMS = ("json", "yes")      # 入力に入れないもの（--json はいつも付ける。--yes は確認のあるものにいつも付ける）
GLOBAL_OPTIONS = ("-C", "--directory")
CONFIRM_OPTION = "--yes"
SCHEMA_TYPES = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}
PYTHON_TYPES = {"str": (str,), "int": (int,), "float": (int, float), "bool": (bool,)}


@dataclass(frozen=True)
class Context:
    """MCP サーバーを起動したエージェント。registration：登録（ecobuild_agent.registry.Registration）。
    kind：owner（タスクの持ち主）か helper（手伝い）。workspace：作業空間の場所。host_run：ビルド・テスト等をこのPCで
    実行するツールを渡すか（起動した ECOBuild が、このPCの設定で決める）。"""
    agent_id: str
    registration: Any
    kind: str
    workspace: Path
    host_run: bool = False


Provider = Callable[[Context], "list[Tool]"]
_providers: list[Provider] = []


def register_provider(fn: Provider) -> Provider:
    """ツールを足す関数（Context → ツールの並び）を登録する。デコレーターとしても使える。"""
    if fn not in _providers:
        _providers.append(fn)
    return fn


def tool_name(path: str) -> str:
    """コマンドの道筋（"task status"）→ ツールの名前（"task_status"）。"""
    return "_".join(path.split())


def command_nodes(catalog: dict) -> list[dict]:
    """--help --json の一覧のうち、印の付いた実行できるコマンド（共通のものと、今いるモジュールの型のもの）。"""
    trees = [catalog.get("commands", [])]
    typed = (catalog.get("types") or {}).get(catalog.get("type") or "")
    if typed:
        trees.append(typed.get("commands", []))
    found: list[dict] = []

    def walk(nodes):
        for node in nodes:
            if node.get("runnable") and node.get("agent") in MARKS:
                found.append(node)
            walk(node.get("commands", []))

    for tree in trees:
        walk(tree)
    return found


def _inputs(node: dict) -> list[dict]:
    """入力にする引数・オプション（kind：argument・option を付けたもの）。"""
    found = [{**argument, "kind": "argument"} for argument in node.get("arguments", [])]
    found += [{**option, "kind": "option"} for option in node.get("options", [])
              if option.get("param") not in HIDDEN_PARAMS and not set(option.get("names", [])) & set(GLOBAL_OPTIONS)]
    return [item for item in found if item.get("param")]


def _many(item: dict) -> bool:
    return bool(item.get("multiple"))


def input_schema(node: dict) -> dict:
    """コマンドの入力の形（JSON Schema）。"""
    properties, required = {}, []
    for item in _inputs(node):
        kind = SCHEMA_TYPES.get(item.get("type"), "string")
        prop: dict = {"type": "array", "items": {"type": kind}} if _many(item) else {"type": kind}
        if item.get("help"):
            prop["description"] = item["help"]
        if item.get("choices"):
            target = prop["items"] if _many(item) else prop
            target["enum"] = list(item["choices"])
        if item.get("default") is not None and not _many(item):
            prop["default"] = item["default"]
        properties[item["param"]] = prop
        if item.get("required"):
            required.append(item["param"])
    schema: dict = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def to_argv(node: dict, arguments: dict) -> list[str]:
    """入力 → ecobuild に渡す引数（道筋は含めない）。--json は付ける。確認のあるコマンドには --yes も。"""
    inputs = {item["param"]: item for item in _inputs(node)}
    unknown = sorted(set(arguments) - set(inputs))
    if unknown:
        raise ToolError(f"知らない入力です：{', '.join(unknown)}（使える入力：{', '.join(inputs) or 'なし'}）")
    options: list[str] = []
    positional: list[str] = []
    for param, item in inputs.items():
        if param not in arguments or arguments[param] is None:
            if item.get("required"):
                raise ToolError(f"{param} を指定してください。")
            continue
        values = _values(param, item, arguments[param])
        if item["kind"] == "argument":
            positional += [_text(value) for value in values]
        elif item.get("flag"):
            value = values[0]
            if value != bool(item.get("default")):
                if value:
                    options.append(item["names"][0])
                elif item.get("negative"):
                    options.append(item["negative"])
        else:
            for value in values:
                options += [item["names"][0], _text(value)]
    argv = [*options, "--json"]
    if any(CONFIRM_OPTION in option.get("names", []) for option in node.get("options", [])):
        argv.append(CONFIRM_OPTION)
    if any(value.startswith("-") for value in positional):
        argv.append("--")
    return argv + positional


def _values(param: str, item: dict, value: Any) -> list:
    if _many(item):
        if not isinstance(value, list):
            raise ToolError(f"{param} は配列で指定してください。")
        values = value
    else:
        if isinstance(value, list):
            raise ToolError(f"{param} は1つの値で指定してください。")
        values = [value]
    expected = PYTHON_TYPES.get(item.get("type"), (str,))
    for one in values:
        if not isinstance(one, expected) or (bool not in expected and isinstance(one, bool)):
            raise ToolError(f"{param} の値の型が違います（{SCHEMA_TYPES.get(item.get('type'), 'string')}）：{one!r}")
    return values


def _text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def _description(node: dict) -> str:
    text = node.get("default_help") or node.get("help") or node.get("summary") or ""
    return text or node["path"]


Runner = Callable[[list[str]], dict]


def command_tools(catalog: dict, run: Runner) -> list[tuple[str, Tool]]:
    """印の付いたコマンドのツール（印, ツール）。run：ecobuild に渡す引数（-C の後）→ JSON の文書。"""
    tools = []
    for node in command_nodes(catalog):
        def call(arguments: dict, node=node) -> dict:
            return run([*node["path"].split(), *to_argv(node, arguments)])
        tools.append((node["agent"], Tool(tool_name(node["path"]), _description(node), input_schema(node), call)))
    return tools


def tools(context: Context, catalog: dict, run: Runner, allows: Callable[[Any, str], bool]) -> list[Tool]:
    """このエージェントに渡すツール：印の付いたコマンド（手伝いには owner を除く）と、足したツール。どれも登録で許したもの。"""
    found = [tool for mark, tool in command_tools(catalog, run) if context.kind != HELPER or mark != OWNER]
    for provider in _providers:
        found += provider(context)
    result, seen = [], set()
    for tool in found:
        if tool.name not in seen and allows(context.registration, tool.name):
            seen.add(tool.name)
            result.append(tool)
    return result


def runner(program: Iterable[str], workspace: Path) -> Runner:
    """ecobuild -C <作業空間> <引数> を実行して、出力の JSON の文書を返すもの。program：ecobuild を起動するコマンド。"""
    program = list(program)

    def run(argv: list[str]) -> dict:
        completed = subprocess.run([*program, "-C", str(workspace), *argv], capture_output=True, encoding="utf-8",
                                   errors="replace", stdin=subprocess.DEVNULL,
                                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        document = _document(completed.stdout)
        if document is None:
            message = ((_messages(completed.stderr) or completed.stdout).strip()[-2000:]
                       or f"終了コード {completed.returncode}")
            return {"ok": False, "command": " ".join(argv), "result": None,
                    "error": {"code": "unexpected_error", "message": message}, "exit_code": completed.returncode}
        return document

    return run


def _messages(stderr: str) -> str:
    """ecobuild --json の標準エラー（1行1件の JSON のイベント。--help --json の events）から、ツール・プログラムの出力を
    除いた文（JSON でない行はそのまま）。"""
    found = []
    for line in (stderr or "").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            event = None
        if not isinstance(event, dict) or not isinstance(event.get("text"), str):
            found.append(line)
        elif event.get("kind") != "output":
            found.append(event["text"])
    return "\n".join(found)


def _document(output: str) -> dict | None:
    """出力の最後の JSON の文書（その前にほかの行があってもよい）。"""
    for line in reversed(output.strip().splitlines()):
        try:
            found = json.loads(line)
        except ValueError:
            continue
        if isinstance(found, dict):
            return found
    try:
        found = json.loads(output)
    except ValueError:
        return None
    return found if isinstance(found, dict) else None


def read_catalog(run: Runner) -> dict:
    """ecobuild -C <作業空間> --help --json の一覧。読めなければ EcoBuildError。"""
    document = run(["--help", "--json"])
    if not document.get("ok") or not isinstance(document.get("result"), dict):
        from ecobuild.errors import EcoBuildError

        from .errors import ErrorCode
        error = document.get("error") or {}
        raise EcoBuildError(ErrorCode.AGENT_ERROR, "ECOBuild のコマンドの一覧を読めませんでした："
                            + (error.get("message") or "出力が JSON ではありません"))
    return document["result"]


def instructions(context: Context) -> str:
    return (f"ECOBuild のモジュールの作業空間（{context.workspace.as_posix()}）で作業するためのツールです。"
            "ビルド・テスト・実行・タスクの操作は、このツールで行います。"
            "ECOBuild のコマンドのツールは、そのコマンドの --json の結果（ok・result・error 等）をそのまま返します。")


def server(context: Context, run: Runner, allows: Callable[[Any, str], bool]) -> Server:
    """エージェントの MCP サーバー（一覧を1回読んで、ツールを決める）。"""
    return Server(tools(context, read_catalog(run), run, allows), name="ecobuild-agent", version=_version(),
                  instructions=instructions(context))


def serve(context: Context, program: Iterable[str], allows: Callable[[Any, str], bool],
          stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    """標準入出力で、入力が閉じるまで答え続ける。"""
    return server(context, runner(program, context.workspace), allows).serve(stdin, stdout)


def _version() -> str:
    from importlib import metadata
    try:
        return metadata.version("ecobuild")
    except metadata.PackageNotFoundError:
        return "0"
