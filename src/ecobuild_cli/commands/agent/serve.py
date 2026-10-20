import json as _json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Annotated

import click
import ecobuild_container as container
from ecobuild_agent import serve as agent_serve
from ecobuild_agent import team

from ..._output import Invocation, execute
from ..container._source import source


def command(json: Annotated[bool, "出来事を1行ずつJSONで出力し、返事を標準入力から読む（係を起動するアプリ向け）"] = False) -> int:
    """ECOBuild の係（エージェントの間の取り次ぎ）を、止めるまで動かし続けます。

    コンテナの中・GUI の窓の中の進行役が頼んだチームの操作（agent team start/close/send）をこのPCで実行し、作業役の
    返答が終わったら進行役の受け箱に知らせを入れます。このPCに1つだけ動かします（GUI は自分で起動します）。
    --json：作業役を起動してほしい（agent-start）・止めてほしい（agent-stop）を出来事として1行ずつ出します。止めたら
    {"ack": <key>} を標準入力に1行で返します。標準入力が閉じると終わります。--json なしでは、作業役は新しい画面で起動します。
    """
    stop = threading.Event()
    acks: dict[str, threading.Event] = {}
    lock = threading.Lock()

    def emit(event: dict) -> None:
        with lock:
            click.echo(_json.dumps(event, ensure_ascii=False))

    def ack(key: str, timeout: float) -> bool:
        return acks.setdefault(key, threading.Event()).wait(timeout)

    def listen() -> None:   # 起動したアプリからの返事。閉じたら終わる
        for line in sys.stdin:
            try:
                key = _json.loads(line).get("ack")
            except (ValueError, AttributeError):
                continue
            if key:
                acks.setdefault(str(key), threading.Event()).set()
        stop.set()

    def open_agent(path: Path, role: str, prompt: str) -> None:
        from ..._module import Module
        Module.find(path).start_agent(source=source(), progress=log, role=role, prompt=prompt)

    def log(message: str) -> None:
        click.echo(message, err=True)

    def action(inv):
        with agent_serve.Lock():
            serve = agent_serve.Serve(run, emit=emit if json else None, ack=ack,
                                      open_agent=None if json else open_agent, log=log)
            log("ECOBuild の係を動かしています" + ("（止めるには Ctrl+C）" if not json else ""))
            if json:
                threading.Thread(target=listen, daemon=True).start()
            try:
                agent_serve.serve_forever(serve, stop)
            except KeyboardInterrupt:
                pass
        return {"stopped": True}

    return execute("agent serve", Invocation(json_output=json), action, lambda r: "ECOBuild の係を止めました。")


def run(args: list[str], cwd: Path) -> dict:
    """この ECOBuild のコマンドを cwd で実行し、その JSON の結果を返す。頼みとしてではなく、このPCで直接実行する
    （窓の中・コンテナの中の印は渡さない）。"""
    env = {key: value for key, value in os.environ.items() if key not in (team.WINDOW_VARIABLE, container.INSIDE)}
    env["PYTHONIOENCODING"] = "utf-8"
    args = [*args, *([] if "--json" in args else ["--json"])]
    try:
        done = subprocess.run([sys.executable, "-m", "ecobuild_cli", "-C", str(cwd), *args], capture_output=True,
                              encoding="utf-8", errors="replace", env=env, timeout=team.REQUEST_TIMEOUT,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as error:
        return agent_serve.failed(f"ecobuild を実行できませんでした：{error}")
    lines = [line for line in (done.stdout or "").splitlines() if line.strip()]
    try:
        return _json.loads(lines[-1])
    except (IndexError, ValueError):
        return agent_serve.failed((done.stderr or "ecobuild の結果を読めませんでした。").strip()[-2000:])
