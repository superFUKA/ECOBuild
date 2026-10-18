"""画面を開かずに、エージェントに1回話しかけて返答を待つ（会話は session で続ける）。

Claude Code の `claude -p`（発言は標準入力から）を stream-json で動かし、返答の文と、途中で実行したコマンドを返す。
画面のない使い方（別のアプリの会話の窓など）のためのもの。許可されていない道具は、聞かれずに断られる。
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import AgentError, ErrorCode
from .launch import DEFAULT_COMMAND

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Action:
    """返答の途中で使った道具（シェルのコマンドなら command）と、その結果。"""
    tool: str
    command: str
    ok: bool | None = None
    output: str = ""


@dataclass(frozen=True)
class Reply:
    session: str | None
    text: str
    ok: bool
    actions: tuple[Action, ...] = ()


def ask(directory: Path | str, text: str, *, session: str | None = None,
        command: list[str] | tuple[str, ...] = DEFAULT_COMMAND, settings: Path | str | None = None,
        timeout: float | None = None) -> Reply:
    """directory で text を1回話しかける。session を渡すと、その会話の続き。
    settings：許可・フックの設定のファイル（kit の settings）。フォルダーの .claude/settings.json の許可は、そのフォルダーを
    画面で一度「信頼」するまで使われないので、画面のない使い方ではファイルで渡す。"""
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise AgentError(ErrorCode.DIRECTORY_NOT_FOUND, f"フォルダーが見つかりません：{directory}")
    if not text.strip():
        raise AgentError(ErrorCode.EMPTY_PROMPT, "話しかける文が空です。")
    if not command or (program := shutil.which(command[0])) is None:
        name = command[0] if command else "（空）"
        raise AgentError(ErrorCode.AGENT_NOT_FOUND, f"エージェント {name} が見つかりません。",
                         hint=f"{name} をインストールし、PATH から実行できるようにしてください。")
    args = [program, *command[1:], "-p", "--output-format", "stream-json", "--verbose"]
    if settings:
        args += ["--settings", str(settings)]
    if session:
        args += ["--resume", session]
    try:
        done = subprocess.run(args, cwd=directory, input=text, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise AgentError(ErrorCode.TIMEOUT, f"エージェントの返答が {timeout:g} 秒で終わりませんでした。") from error
    except OSError as error:
        raise AgentError(ErrorCode.LAUNCH_FAILED, f"エージェントを起動できませんでした：{error}") from error
    logger.debug("agent asked", extra={"data": {"args": args, "cwd": str(directory), "code": done.returncode}})
    reply = parse(done.stdout)
    if reply is None:
        tail = (done.stderr or done.stdout).strip().splitlines()[-5:]
        raise AgentError(ErrorCode.ASK_FAILED, "エージェントから返答がありませんでした。" + ("\n" + "\n".join(tail) if tail else ""))
    return reply


def parse(output: str) -> Reply | None:
    """stream-json の出力を読む。終わりの印（result）がなければ None。"""
    session = None
    actions: dict[str, Action] = {}
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
                    tool_input = block.get("input") or {}
                    actions[block.get("id", "")] = Action(block.get("name", ""), tool_input.get("command", ""))
                elif block.get("type") == "text":
                    texts.append(block.get("text", ""))
        elif event.get("type") == "user" and isinstance(content, list):
            for block in filter(lambda b: isinstance(b, dict), content):
                if block.get("type") == "tool_result" and block.get("tool_use_id") in actions:
                    key = block["tool_use_id"]
                    actions[key] = Action(actions[key].tool, actions[key].command, not block.get("is_error"),
                                          _text(block.get("content")))
        elif event.get("type") == "result":
            text = event.get("result") if isinstance(event.get("result"), str) else (texts[-1] if texts else "")
            return Reply(event.get("session_id") or session, text, not event.get("is_error"), tuple(actions.values()))
    return None


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""
