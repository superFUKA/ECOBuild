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

from ..._output import Invocation, execute
from ..container._source import source


def command(json: Annotated[bool, "出来事を1行ずつJSONで出力し、返事を標準入力から読む（係を起動するアプリ向け）"] = False) -> int:
    """ECOBuild の係（エージェントの間の取り次ぎ）を、止めるまで動かし続けます。

    コンテナの中のエージェントが頼んだ子の操作（MCP のツール children_*・report_to_parent）と、人が頼んだ操作
    （agent restart・takeover・handback・close 等）をこのPCで実行し、子の返答が終わったら親の受け箱に知らせを入れます。
    このPCに1つだけ動かします（GUI は自分で起動します）。エージェントが起動した子は、係が画面なし（アプリ用の起動。
    コンテナの中の claude -p）で動かします。係を止めると、子は返答を終えてから止まり、次に係を動かすと前の会話の続き
    から起きます。
    --json：人の画面（対話型）のエージェントを止めてほしい（agent-stop）・人の画面で開いてほしい（agent-start）を
    出来事として1行ずつ出します。済んだら {"ack": <key>} を標準入力に1行で返します。標準入力が閉じると終わります。
    """
    stop = threading.Event()
    acks: dict[str, threading.Event] = {}
    lock = threading.Lock()

    def emit(event: dict) -> None:
        with lock:
            click.echo(_json.dumps(event, ensure_ascii=False))

    def ack(key: str, timeout: float) -> bool:
        return acks.setdefault(key, threading.Event()).wait(timeout)

    def listen(replies) -> None:   # 起動したアプリからの返事。閉じたら終わる
        for line in replies:
            try:
                key = _json.loads(line).get("ack")
            except (ValueError, AttributeError):
                continue
            if key:
                acks.setdefault(str(key), threading.Event()).set()
        stop.set()

    def launch(agent_id: str, resume: str, progress):
        from ecobuild_agent import agents
        from ..._module import Module
        record = agents.load(agent_id)
        return Module.find(record.workspace).app_launch(agent_id, resume=resume, source=source(), progress=progress)

    def find(path):
        from ..._module import Module
        return Module.find(path)

    def log(message: str) -> None:
        click.echo(message, err=True)

    def action(inv):
        with agent_serve.Lock():
            serve = agent_serve.Serve(run, emit=emit if json else None, ack=ack, launch=launch, find=find, log=log)
            log("ECOBuild の係を動かしています" + ("（止めるには Ctrl+C）" if not json else ""))
            if json:
                threading.Thread(target=listen, args=(detach_stdin(),), daemon=True).start()
            serve.wake()   # 前の係が動かしていたエージェントを引き継ぐ（終わったものから続きから起こす）
            try:
                agent_serve.serve_forever(serve, stop)
            except KeyboardInterrupt:
                pass
            serve.close()   # 動かしているエージェントの入力を閉じる（返答を終えて止まる。次の係が続きから起こす）
            # 実行中の頼みは少し待って終えさせ、終わらないものは止める（残すと、止まったまま ecobuild を使い続け、
            # 入れ替え〔インストーラー〕を止める。頼んだ側は、係の途中経過が途切れたことで失敗と分かる）
            if not serve.wait(STOP_GRACE):
                for pid in list(_running):
                    agent_status.stop(pid)
                serve.wait(10)
        return {"stopped": True}

    return execute("agent serve", Invocation(json_output=json), action, lambda r: "ECOBuild の係を止めました。")


def detach_stdin():
    """標準入力（起動したアプリの返事のパイプ）を係だけのものにして返し、標準入力は空にする。係が起動するものはすべて
    （ecobuild・git 等）標準入力を引き継ぐが、Windows では読みかけのパイプを引き継いだプロセスが起動の途中で止まる
    （git が止まり、頼みが進まなかった）。"""
    replies = os.fdopen(os.dup(sys.stdin.fileno()), encoding="utf-8", errors="replace")   # 複製は子に引き継がれない
    empty = os.open(os.devnull, os.O_RDONLY)
    os.dup2(empty, 0)   # Windows でも標準入力のハンドルが差し替わる（子が引き継ぐのはこちら）
    os.close(empty)
    sys.stdin = open(os.devnull, encoding="utf-8")
    return replies


def type_has(args: list[str], cwd: Path) -> bool:
    """args が型のコマンドなら、cwd のモジュールの型が持っているか（型のコマンドでなければ True）。"""
    from ... import _types
    route = tuple(a for a in args[:2] if not a.startswith("-"))
    owners = [name for name, routes in _types.all_routes().items() if route in routes]
    if not owners:
        return True
    found = _types.package(_types.current(cwd))
    return found is not None and route in _types.routes(found)


PROGRAM = (sys.executable, "-m", "ecobuild_cli")   # 係が頼みを実行する ECOBuild（この ECOBuild と同じもの）
STOP_GRACE = 8          # 係を止めるとき、実行中の頼みが終わるのを待つ秒数（アプリは止めてからこれより長く待つ）
_running: set[int] = set()   # 実行中の ecobuild（係を止めるときに残さない）


def run(args: list[str], cwd: Path, progress=None, stall: float | None = None) -> dict:
    """この ECOBuild のコマンドを cwd で実行し、その JSON の結果を返す。頼みとしてではなく、このPCで直接実行する
    （コンテナの中の印は渡さない）。標準入力は渡さない：係は起動したアプリの返事を読み続けており、Windows では
    読みかけのパイプを引き継いだ Python が起動の途中で止まる（頼んだ側が待ち続けた）。
    progress(line)：コマンドの経過（標準エラーの1行ずつ）。stall：経過がこの秒数出なければ、止まったとみなして止める。"""
    if not type_has(args, cwd):   # 型のコマンドを、その型でないモジュールで実行しない（返答のたびの project update 等）
        return agent_serve.failed(f"{' '.join(args[:2])} はこのモジュールの型のコマンドではありません。")
    env = {key: value for key, value in os.environ.items() if key != container.INSIDE}
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
        elif now - started > agent_serve.children.REQUEST_TIMEOUT:
            stopped = f"ecobuild が {agent_serve.children.REQUEST_TIMEOUT} 秒で終わりませんでした。止めました。"
        if stopped:
            agent_status.stop(process.pid)
            process.wait()
            return agent_serve.failed(stopped, hint="途中までできたもの（子タスク・作業空間）がないか確かめてから、"
                                                    "やり直してください。")
        time.sleep(0.2)
    for reader in readers:
        reader.join(5)
    lines = [line for line in "".join(out).splitlines() if line.strip()]
    try:
        return _json.loads(lines[-1])
    except (IndexError, ValueError):
        return agent_serve.failed(("".join(err) or "ecobuild の結果を読めませんでした。").strip()[-2000:])
