"""ecoagent.mcp：決まったツールだけを渡す MCP のサーバー（標準入出力の JSON-RPC）。"""

import io
import json

from ecoagent.mcp import INVALID_PARAMS, METHOD_NOT_FOUND, PARSE_ERROR, Server, Tool, ToolError


def _echo(arguments):
    return {"ok": True, "result": arguments}


def _broken(arguments):
    raise ToolError("こわれています")


TOOLS = [
    Tool("echo", "入力をそのまま返す", {"type": "object", "properties": {"text": {"type": "string"}}}, _echo),
    Tool("fail", "失敗を返す", {"type": "object", "properties": {}}, lambda arguments: {"ok": False, "error": {}}),
    Tool("broken", "誤りを投げる", {"type": "object", "properties": {}}, _broken),
]


def _server():
    return Server(TOOLS, name="test", version="1.2", instructions="試験のツールです。")


def _request(method, params=None, ident=1):
    return {"jsonrpc": "2.0", "id": ident, "method": method, **({"params": params} if params is not None else {})}


def test_initialize_names_itself_and_follows_the_client_version():
    answer = _server().handle(_request("initialize", {"protocolVersion": "2025-03-26"}))
    result = answer["result"]
    assert answer["id"] == 1 and result["protocolVersion"] == "2025-03-26"
    assert result["serverInfo"] == {"name": "test", "version": "1.2"} and result["capabilities"] == {"tools": {}}
    assert result["instructions"] == "試験のツールです。"
    assert _server().handle(_request("initialize"))["result"]["protocolVersion"] == "2025-06-18"


def test_ping_and_notifications():
    assert _server().handle(_request("ping")) == {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert _server().handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list_gives_only_the_tools():
    tools = _server().handle(_request("tools/list"))["result"]["tools"]
    assert [t["name"] for t in tools] == ["echo", "fail", "broken"]
    assert tools[0] == {"name": "echo", "description": "入力をそのまま返す",
                        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}}


def test_tools_call_returns_the_result_as_text():
    result = _server().handle(_request("tools/call", {"name": "echo", "arguments": {"text": "あ"}}))["result"]
    assert result["isError"] is False
    assert json.loads(result["content"][0]["text"]) == {"ok": True, "result": {"text": "あ"}}
    result = _server().handle(_request("tools/call", {"name": "fail"}))["result"]
    assert result["isError"] is True                                   # ok が False
    result = _server().handle(_request("tools/call", {"name": "broken", "arguments": {}}))["result"]
    assert result == {"content": [{"type": "text", "text": "こわれています"}], "isError": True}


def test_unknown_tool_and_method_are_errors():
    answer = _server().handle(_request("tools/call", {"name": "nosuch"}))
    assert answer["error"]["code"] == INVALID_PARAMS and "nosuch" in answer["error"]["message"]
    assert _server().handle(_request("resources/list"))["error"]["code"] == METHOD_NOT_FOUND


def test_serve_answers_line_by_line_until_the_input_closes():
    lines = [json.dumps(_request("ping", ident=1)), "", "壊れた",
             json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
             json.dumps(_request("tools/list", ident="b"))]
    out = io.StringIO()
    assert _server().serve(io.StringIO("\n".join(lines) + "\n"), out) == 0
    answers = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [a["id"] for a in answers] == [1, None, "b"]
    assert answers[1]["error"]["code"] == PARSE_ERROR
