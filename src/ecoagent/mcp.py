"""MCP（Model Context Protocol）のサーバー：標準入出力の JSON-RPC で、決まったツールだけをエージェントに渡す。

ecobuild 等を知らない。ツール（Tool：名前・説明・入力の形・呼ぶ関数）は使う側が作って渡す。
- 答えるのは initialize・ping・tools/list・tools/call。知らないメソッドは method not found。通知（id のないもの）には答えない。
- ツールを呼んだ結果（dict）は、JSON の文字にして返す。結果の ok が False なら isError。
  ToolError を投げたら、その文を isError で返す（ツールの中の誤り。JSON-RPC の誤りにはしない）。
- 知らないツールの名前は、JSON-RPC の誤り（invalid params）。
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterable, TextIO

PROTOCOL = "2025-06-18"     # こちらの版（相手が版を名乗れば、それに合わせる）
PARSE_ERROR = -32700
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


@dataclass(frozen=True)
class Tool:
    """エージェントに渡すツール。input_schema：入力の形（JSON Schema の object）。call：入力 → 結果。"""
    name: str
    description: str
    input_schema: dict
    call: Callable[[dict], dict]

    def listed(self) -> dict:
        """tools/list に出す形。"""
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}


class ToolError(Exception):
    """ツールの中の誤り（エージェントに文で返す）。"""


class Server:
    """ツールの一覧を持ち、JSON-RPC の要求1つに答える。name・version・instructions は initialize で名乗るもの。"""

    def __init__(self, tools: Iterable[Tool], *, name: str, version: str = "0", instructions: str = ""):
        self.tools = {tool.name: tool for tool in tools}
        self.name = name
        self.version = version
        self.instructions = instructions

    def handle(self, request: Any) -> dict | None:
        """要求1つ（読んだ JSON）への答え。通知なら None。"""
        if not isinstance(request, dict):
            return _error(None, INVALID_PARAMS, "invalid request")
        method, ident = request.get("method"), request.get("id")
        if ident is None:          # 通知（notifications/initialized 等）
            return None
        params = request.get("params") or {}
        if method == "initialize":
            result: dict = {"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": self.name, "version": self.version}}
            if self.instructions:
                result["instructions"] = self.instructions
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [tool.listed() for tool in self.tools.values()]}
        elif method == "tools/call":
            tool = self.tools.get(params.get("name", ""))
            if tool is None:
                return _error(ident, INVALID_PARAMS, f"unknown tool: {params.get('name')}")
            result = self.call(tool, params.get("arguments") or {})
        else:
            return _error(ident, METHOD_NOT_FOUND, f"method not found: {method}")
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    @staticmethod
    def call(tool: Tool, arguments: dict) -> dict:
        try:
            value = tool.call(arguments)
        except ToolError as error:
            return {"content": [{"type": "text", "text": str(error)}], "isError": True}
        failed = isinstance(value, dict) and value.get("ok") is False
        return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2)}],
                "isError": failed}

    def serve(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
        """標準入力から1行に1つの要求を読み、答えを1行ずつ書く。入力が閉じたら終わる。"""
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
            except ValueError:
                answer: dict | None = _error(None, PARSE_ERROR, "parse error")
            else:
                answer = self.handle(request)
            if answer is not None:
                stdout.write(json.dumps(answer, ensure_ascii=False) + "\n")
                stdout.flush()
        return 0


def _error(ident: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}
