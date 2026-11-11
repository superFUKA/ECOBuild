"""このPCで実行するツール（host_run）：コンテナの中のエージェントが、ビルド・テスト・実行・確認をこのPC（Windows 等）で行う。

作業空間ごとに人が許したとき（inside.host_run。container set --host-run on）だけ渡す。起動した ECOBuild が MCP サーバーに
--host-run を付け（Context.host_run）、ツールは頼みとして係に渡す。係はこのPCの設定をもう一度確かめてから、
ecobuild host <コマンド> <引数> --json を作業空間で実行する（ファイルは同じ。コンテナの中には渡さない）。
エージェントの書いたコードが、コンテナの守りなしにこのPCで動く：既定は許さない。
"""

from __future__ import annotations

from ecobuild.errors import EcoBuildError
from ecoagent.mcp import Tool, ToolError

from . import mcp
from .errors import ErrorCode

TOOL = "host_run"
COMMANDS = ("build", "test", "run", "clean", "rebuild", "check")   # ecobuild host で実行できるもの（CLI の _inside.COMMANDS）
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["command"],
          "properties": {"command": {"type": "string", "enum": list(COMMANDS), "description": "このPCで実行する ECOBuild のコマンド"},
                         "args": {"type": "array", "items": {"type": "string"},
                                  "description": "コマンドの引数（例 [\"--filter\", \"foo\"]。場所は作業空間からの相対で。"
                                                 "--json は付けなくてよい）"}}}
DESCRIPTION = ("ECOBuild のビルド・テスト・実行・確認（build・test・run・clean・rebuild・check）を、コンテナの中ではなく"
               "このPC（人が使っている Windows 等）で実行します（ecobuild host <コマンド>）。ファイルは同じものを使います。"
               "このPCの環境でしか確かめられないことに使います。結果はそのコマンドの --json の結果です。")


def check_arguments(arguments) -> dict:
    """ツールの入力を形と照らす（係の側で）。"""
    if not isinstance(arguments, dict):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "ツールの入力は object です。")
    unknown = sorted(set(arguments) - set(SCHEMA["properties"]))
    if unknown:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"知らない入力です：{', '.join(unknown)}")
    if arguments.get("command") not in COMMANDS:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"command は {'・'.join(COMMANDS)} のどれかです：{arguments.get('command')}")
    args = arguments.get("args") or []
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "args は文字列の配列です。")
    if any(a in ("-C", "--directory") or a.startswith("--directory=") for a in args):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "作業空間の外では実行できません（-C は使えません）。")
    return {"command": arguments["command"], "args": args}


def argv(arguments: dict) -> list[str]:
    """係が作業空間で実行する ecobuild の引数。"""
    args = [a for a in arguments["args"] if a != "--json"]
    return ["host", arguments["command"], *args, "--json"]


@mcp.register_provider
def tools(context: mcp.Context) -> list[Tool]:
    """許した作業空間（context.host_run）のエージェントにだけ渡す。実行は頼みとして係に渡す。"""
    if not context.host_run:
        return []
    from . import children

    def run(arguments: dict) -> dict:
        try:
            return children.forward(children.requests_folder(context.agent_id),
                                    {"tool": TOOL, "arguments": arguments, "agent": context.agent_id})
        except EcoBuildError as error:
            raise ToolError(error.message + (f"（{error.hint}）" if error.hint else "")) from error
    return [Tool(TOOL, DESCRIPTION, SCHEMA, run)]
