import json as _json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Annotated

import click
import ecobuild_container as container
from ecobuild_agent import serve as agent_serve
from ecobuild_agent import status as agent_status
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

    def open_agent(path: Path, role: str, prompt: str, agent: str = "") -> None:
        from ..._module import Module
        options = {"source": source(), "progress": log, "role": role, "prompt": prompt}
        module = Module.find(path)
        module.start_agent(agent.split(), **options) if agent.strip() else module.start_agent(**options)

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
            # 実行中の頼みは少し待って終えさせ、終わらないものは止める（残すと、止まったまま ecobuild を使い続け、
            # 入れ替え〔インストーラー〕を止める。頼んだ側は、係の途中経過が途切れたことで失敗と分かる）
            if not serve.wait(STOP_GRACE):
                for pid in list(_running):
                    agent_status.stop(pid)
                serve.wait(10)
        return {"stopped": True}

    return execute("agent serve", Invocation(json_output=json), action, lambda r: "ECOBuild の係を止めました。")


PROGRAM = (sys.executable, "-m", "ecobuild_cli")   # 係が頼みを実行する ECOBuild（この ECOBuild と同じもの）
STOP_GRACE = 8          # 係を止めるとき、実行中の頼みが終わるのを待つ秒数（アプリは止めてからこれより長く待つ）
_running: set[int] = set()   # 実行中の ecobuild（係を止めるときに残さない）


def run(args: list[str], cwd: Path, progress=None, stall: float | None = None) -> dict:
    """この ECOBuild のコマンドを cwd で実行し、その JSON の結果を返す。頼みとしてではなく、このPCで直接実行する
    （窓の中・コンテナの中の印は渡さない）。標準入力は渡さない：係は起動したアプリの返事を読み続けており、Windows では
    読みかけのパイプを引き継いだ Python が起動の途中で止まる（作業役が作られず、頼んだ側が待ち続けた）。
    progress(line)：コマンドの経過（標準エラーの1行ずつ）。stall：経過がこの秒数出なければ、止まったとみなして止める。"""
    env = {key: value for key, value in os.environ.items() if key not in (team.WINDOW_VARIABLE, container.INSIDE)}
    env["PYTHONIOENCODING"] = "utf-8"
    args = [*args, *([] if "--json" in args else ["--json"])]
    try:
        process = subprocess.Popen([*PROGRAM, "-C", str(cwd), *args], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                                   env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                   start_new_session=os.name != "nt")
    except OSError as error:
        return agent_serve.failed(f"ecobuild を実行できませんでした：{error}")
    _running.add(process.pid)
    try:
        return _wait(process, progress, stall)
    finally:
        _running.discard(process.pid)


def _wait(process: subprocess.Popen, progress, stall: float | None) -> dict:
    out, err, last = [], [], [time.monotonic()]

    def read_err() -> None:
        for line in process.stderr:
            err.append(line)
            last[0] = time.monotonic()
            if progress is not None and line.strip():
                progress(line.strip())
    readers = [threading.Thread(target=lambda: out.extend(process.stdout), daemon=True),
               threading.Thread(target=read_err, daemon=True)]
    for reader in readers:
        reader.start()
    started, stopped = time.monotonic(), ""
    while process.poll() is None:
        now = time.monotonic()
        if stall is not None and now - last[0] > stall:
            stopped = f"ecobuild が {int(stall)} 秒、何も進めませんでした（止まっていました）。止めました。"
        elif now - started > team.REQUEST_TIMEOUT:
            stopped = f"ecobuild が {team.REQUEST_TIMEOUT} 秒で終わりませんでした。止めました。"
        if stopped:
            agent_status.stop(process.pid)
            process.wait()
            return agent_serve.failed(stopped, hint="agent team list で、途中までできたもの（子タスク・作業空間）がないか"
                                                    "確かめてから、やり直してください。")
        time.sleep(0.2)
    for reader in readers:
        reader.join(5)
    lines = [line for line in "".join(out).splitlines() if line.strip()]
    try:
        return _json.loads(lines[-1])
    except (IndexError, ValueError):
        return agent_serve.failed(("".join(err) or "ecobuild の結果を読めませんでした。").strip()[-2000:])
