"""ECOBuild の係（このPCで常駐する）：エージェントの間の取り次ぎを、画面を持つアプリから切り離して本体で行う。

- 頼み（team.REQUESTS）：コンテナの中・GUI の窓の中の進行役が書いたチームの操作（agent team …）を、このPCで実行して
  結果を書き戻す（team.forward が待っている）。拾ってから結果を書くまで、途中経過（team.PROGRESS）を毎秒書く
  （頼んだ側は、係が動いているか・何をしているかを見ながら待つ）。
- 進行役への知らせ：作業役の返答が終わったら（Stop フックの replied.json）、進行役の受け箱に入れる（team.lead_notice）。
- 返答が終わったら、作業空間の型に手元をそろえさせる（project update。C++ では Visual Studio の構成。ほかの型は何もしない）。

エージェントを動かしているのは係ではなく、係を起動した側（GUI の窓等）。作業役を起動する・閉じる前に止める、は出来事
（emit）としてその側に頼む（止めるときは返事 ack を待つ）。起動した側がいなければ（端末から起動した）、作業役は
新しい画面で起動し（open_agent）、止めるときはそのプロセスを止める（agent_status.running_pid）。受け箱のものを
届けるのも、エージェントを動かしている側。

ECOBuild のコマンドは run で実行する（使う側が渡す：プログラム名を本体に書かない）。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from pathlib import Path

from ecobuild import settings as _settings
from ecobuild.errors import EcoBuildError

from . import status as agent_status
from . import team
from .errors import ErrorCode

TEAM_COMMANDS = ("start", "close", "send", "list", "restart")
LOCK = Path("agents") / "serve.lock"   # ECOBUILD_HOME の下：係はこのPCに1つ
STOP_TIMEOUT = 30                       # 作業役を止めてもらう返事を待つ秒数

Run = Callable[..., dict]   # run(args, cwd, progress=None, stall=None)


def failed(message: str, hint: str | None = None) -> dict:
    return {"ok": False, "result": None, "error": {"code": ErrorCode.AGENT_ERROR, "message": message, "hint": hint}}


class Serve:
    """係の1回分の見回り（step）と、その状態（返答の終わりを見た時刻）。

    run(args, cwd, progress=None, stall=None)：ECOBuild のコマンドを cwd で実行し、その JSON の結果（{ok, result|error}）を
    返す。progress(line)：コマンドの経過（人向けの1行）。stall：経過がこの秒数出なければ止まったとみなして止める。
    emit(event)：起動した側への出来事（None なら起動した側はいない）。ack(key, timeout)：その返事を待つ（届いたか）。
    open_agent(path, role, prompt, agent)：起動した側がいないときに、作業役を新しい画面で起動する（agent：起動する
    コマンド。空なら既定）。
    log(message)：したことを人に知らせる。

    見回りは待たない：頼みはすぐに受け取り（拾った印 .taken。頼んだ側は拾われたかで係がいるかを見る）、実行は裏で行う。
    同じ置き場所（作業空間）のものは届いた順に1つずつ、ほかの置き場所のものとは並べて（作業役を作る clone 等で長く
    かかっても、ほかのエージェントの頼みを待たせない）。background=False なら、その場で実行する。"""

    def __init__(self, run: Run, *, emit: Callable[[dict], None] | None = None,
                 ack: Callable[[str, float], bool] = lambda key, timeout: True,
                 open_agent: Callable[[Path, str, str, str], None] | None = None,
                 log: Callable[[str], None] = lambda message: None, background: bool = True):
        self.run, self.emit, self.ack, self.open_agent, self.log = run, emit, ack, open_agent, log
        self.background = background
        self.started = time.time()
        self._replied: dict[Path, float] = {}
        self._queues: dict[Path, deque] = {}
        self._busy: set[Path] = set()
        self._guard = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._progress: dict[Path, dict] = {}   # 拾って結果をまだ書いていない頼みの途中経過（ファイル → 中身）

    def step(self) -> None:
        self._beat()
        for folder in agent_status.folders():
            root = agent_status.workspace_of(folder)
            self._requests(folder, root)
            if root is not None:
                self._watch_reply(folder, root)

    def wait(self, timeout: float | None = None) -> bool:
        """裏で行っているものが終わるまで待つ（timeout 秒まで）。すべて終わったか。"""
        until = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._guard:
                running = [thread for thread in self._threads if thread.is_alive()]
                self._threads = running
            if not running:
                return True
            for thread in running:
                thread.join(None if until is None else max(0.0, until - time.monotonic()))
            if until is not None and time.monotonic() >= until:
                return not any(thread.is_alive() for thread in running)

    def _later(self, folder: Path, job: Callable[[], None]) -> None:
        """job を裏で行う（置き場所 folder ごとに届いた順に1つずつ。ほかの置き場所とは並べて）。"""
        if not self.background:
            self._do(job)
            return
        with self._guard:
            self._queues.setdefault(folder, deque()).append(job)
            if folder in self._busy:
                return
            self._busy.add(folder)
            thread = threading.Thread(target=self._drain, args=(folder,), daemon=True)
            self._threads.append(thread)
        thread.start()

    def _drain(self, folder: Path) -> None:
        while True:
            with self._guard:
                if not self._queues[folder]:
                    self._busy.discard(folder)
                    return
                job = self._queues[folder].popleft()
            self._do(job)

    def _do(self, job: Callable[[], None]) -> None:
        try:
            job()
        except Exception as error:   # 1つの失敗で係を止めない
            self.log(f"係の仕事に失敗しました：{error}")

    # ---- 途中経過 ----------------------------------------------------------------------------------------
    def _report(self, file: Path, doing: str | None = None, *, done: bool = False) -> None:
        """頼みの途中経過（file）を書く（doing：していること）。done：結果を書いたので消す。"""
        with self._guard:
            if done:
                self._progress.pop(file, None)
            else:
                entry = self._progress.setdefault(file, {"doing": "", "since": time.time()})
                if doing:
                    entry["doing"] = doing
                entry["at"] = time.time()
                data = dict(entry)
        if done:
            file.unlink(missing_ok=True)
            return
        try:
            agent_status._write(file, data)
        except OSError:
            pass

    def _beat(self) -> None:
        """実行中の頼みの途中経過に、係が動いている印（時刻）を書く。"""
        with self._guard:
            files = list(self._progress)
        for file in files:
            self._report(file)

    # ---- 頼み -------------------------------------------------------------------------------------------
    def _requests(self, folder: Path, root: Path | None) -> None:
        inbox = folder / team.REQUESTS
        for file in sorted(inbox.glob("*.json")) if inbox.is_dir() else ():
            if "." in file.stem:   # 頼みは <id>.json だけ（結果 <id>.result.json 等は拾わない）
                continue
            taken = file.with_suffix(".taken")
            try:
                os.replace(file, taken)       # 拾った（頼んだ側に係がいると分かる）。ほかが拾ったものは飛ばす
            except OSError:
                continue
            self._report(inbox / f"{file.stem}{team.PROGRESS}", "順番を待っています（同じ作業空間の前の頼みを実行中）")
            self._later(folder, lambda taken=taken: self._answer(inbox, taken, root))

    def _answer(self, inbox: Path, taken: Path, root: Path | None) -> None:
        """拾った頼み1つを実行して、結果を書き戻す。"""
        request = agent_status.read(taken)
        report = inbox / f"{taken.stem}{team.PROGRESS}"
        if not isinstance(request, dict) or not request.get("id"):
            taken.unlink(missing_ok=True)
            self._report(report, done=True)
            return
        try:
            doc = self.handle(root, request, progress=lambda line: self._report(report, line))
        except Exception as error:   # 頼んだ側を待たせたままにしない
            doc = failed(f"係が頼みを実行できませんでした：{error}")
        result = inbox / f"{request['id']}.result.json"
        temporary = result.with_name(result.name + ".tmp")
        try:
            temporary.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, result)
        except OSError:
            pass   # 書けなければ、頼んだ側が待ちきれずに止まる
        taken.unlink(missing_ok=True)
        self._report(report, done=True)

    def handle(self, root: Path | None, request: dict, progress: Callable[[str], None] = lambda line: None) -> dict:
        """頼み1つを実行して、結果の JSON（{ok, result|error}）を返す。progress：途中経過。"""
        args = [str(a) for a in request.get("args") or []]
        if args[:2] != ["agent", "team"] or len(args) < 3 or args[2] not in TEAM_COMMANDS:
            return failed(f"この頼みは受け付けません：ecobuild {' '.join(args)}")
        if root is None:
            return failed("頼んだエージェントの作業空間が分かりません。", hint="エージェントを起動し直してください。")
        cwd = (root / str(request.get("cwd") or ".")).resolve()
        if not cwd.is_relative_to(root.resolve()):
            return failed("作業空間の外では実行しません。")
        shown = " ".join(a if len(a) <= 40 else a[:40] + "…" for a in args if a != "--json")
        self.log(f"頼み：ecobuild {shown}（{root}）")
        progress(f"実行しています：ecobuild {shown}")
        if args[2] in ("close", "restart") and len(args) > 3:
            try:
                member = team.find(root, args[3])
            except EcoBuildError as error:
                return {"ok": False, "result": None,
                        "error": {"code": error.code, "message": error.message, "hint": error.hint}}
            progress(f"「{member.name}」のエージェントを止めています…")
            self._stop(member.path)   # 使っているフォルダーは消せない・起動し直す前に止める
            if args[2] == "restart" and "--no-open" not in args:
                args = [*args, "--no-open"]   # 起動は係が（タブで開いてもらう）
        doc = self.run(args, cwd, progress=progress, stall=team.STALL_SECONDS)
        if args[2] in ("start", "restart") and doc.get("ok") and (doc.get("result") or {}).get("path"):
            progress("エージェントを起動しています…")
            doc = {**doc, "result": self._start(doc["result"], root)}
        return doc

    def _start(self, member: dict, lead: Path) -> dict:
        """作った作業役を起動する：起動した側に頼む（タブで開く）か、いなければ新しい画面で。"""
        path = Path(member["path"])
        if self.emit is not None:
            event = {"event": "agent-start", "path": str(path), "name": member.get("name", ""),
                     "role": member.get("role", team.WORKER), "prompt": member.get("prompt", ""), "lead": str(lead)}
            self.emit({**event, "agent": member["agent"]} if member.get("agent") else event)
            return member
        if self.open_agent is not None:
            self.open_agent(path, member.get("role", team.WORKER), member.get("prompt", ""), member.get("agent", ""))
            return {**member, "opened": True}
        return member

    def _stop(self, path: Path) -> None:
        """作業空間 path のエージェントを止めてもらう（起動した側がいなければ、動かしているプロセスを止める）。"""
        if self.emit is None:
            pid = agent_status.running_pid(team.inbox_of(path))
            if pid is not None:
                agent_status.stop(pid)
            return
        key = uuid.uuid4().hex
        self.emit({"event": "agent-stop", "key": key, "path": str(path)})
        if not self.ack(key, STOP_TIMEOUT):
            self.log(f"エージェントを止めた返事が届きませんでした（{path}）。そのまま閉じます。")

    # ---- 返答の終わり ----------------------------------------------------------------------------------------
    def _watch_reply(self, folder: Path, root: Path) -> None:
        replied = agent_status.read(folder / "replied.json")
        at = replied.get("at") if isinstance(replied, dict) else None
        if not isinstance(at, (int, float)):
            return
        before = self._replied.get(folder)
        self._replied[folder] = at
        if at == before or (before is None and at < self.started):   # 見た・係が動く前のもの
            return
        message = replied.get("message") or ""
        self._later(folder, lambda: self.replied(root, message))

    def replied(self, root: Path, message: str) -> None:
        """作業空間 root のエージェントの返答が終わった。"""
        notice = team.lead_notice(root, message)
        if notice is not None:
            lead, text = notice
            agent_status.put(team.inbox_of(lead), text, sender=str(root))
            self.log(f"進行役に知らせました：{text.splitlines()[0]}")
        self.run(["project", "update"], root)   # 型に手元をそろえさせる（持たない型は not_supported。気にしない）


# ---- 常駐 ----------------------------------------------------------------------------------------------------

class Lock:
    """このPCで係を1つにする（ファイルの排他ロック。終われば OS が外す）。"""

    def __init__(self):
        self.path = _settings.home() / LOCK
        self._file = None

    def __enter__(self) -> Lock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            file.close()
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "ECOBuild の係（agent serve）は、このPCでもう動いています。",
                                hint="係は1つだけ動かします（GUI が起動していることがあります）。") from None
        self._file = file
        return self

    def __exit__(self, *exc) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


def serve_forever(serve: Serve, stop: threading.Event, interval: float = 1.0) -> None:
    """stop が立つまで見回り続ける。"""
    while not stop.is_set():
        try:
            serve.step()
        except Exception as error:   # 1回の失敗で係を止めない
            serve.log(f"見回りに失敗しました：{error}")
        stop.wait(interval)
