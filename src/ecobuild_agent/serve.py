"""ECOBuild の係（このPCで常駐する）：エージェントの間の取り次ぎを、画面を持つアプリから切り離して本体で行う。

- 頼み（team.REQUESTS）：コンテナの中・GUI の窓の中の進行役が書いたチームの操作（agent team …）を、このPCで実行して
  結果を書き戻す（team.forward が待っている）。拾ってから結果を書くまで、途中経過（team.PROGRESS）を毎秒書く
  （頼んだ側は、係が動いているか・何をしているかを見ながら待つ）。
- 進行役への知らせ：作業役の返答が終わったら（Stop フックの replied.json）、進行役の受け箱に入れる（team.lead_notice。
  作業空間・GitHub を調べた事実と注意を添える：裏で行うので見回りは止まらない）。
- 返答が終わったら、作業空間の型に手元をそろえさせる（project update。C++ では Visual Studio の構成。ほかの型は何もしない）。
- AI（進行役の頼み）が起動するエージェントは、係がアプリ用の起動で持つ（app。GUI がいてもいなくても同じ。コンテナでだけ）：
  作業役を作った・起動し直したら起動し、閉じる・起動し直す前に止め、受け箱のものを標準入力へ入れる。人が引き取る
  （takeover：止めて会話の ID を返す。人は対話型で claude --resume）・返す（handback）、人がアプリ用で起動する
  （agent start --app・agent stop）も係が行う。係が終わるときは止め（返答を終えさせてから）、次の係が続きから起こす。

人が起動したもの（対話型）を動かしているのは、係を起動した側（GUI の窓等）。閉じる前に止める、は出来事（emit）として
その側に頼む（返事 ack を待つ）。起動した側がいなければ、そのプロセスを止める（agent_status.running_pid）。

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

from . import app
from . import status as agent_status
from . import team
from .errors import ErrorCode

TEAM_COMMANDS = ("start", "close", "send", "list", "restart", "log", "takeover", "handback")
LOCK = Path("agents") / "serve.lock"   # ECOBUILD_HOME の下：係はこのPCに1つ
STOP_TIMEOUT = 30                       # 作業役を止めてもらう返事を待つ秒数
START_LIMIT = 4                         # 同じ置き場所の作業役の作成（agent team start）を、並べて実行する数

Run = Callable[..., dict]   # run(args, cwd, progress=None, stall=None)


def failed(message: str, hint: str | None = None) -> dict:
    return {"ok": False, "result": None, "error": {"code": ErrorCode.AGENT_ERROR, "message": message, "hint": hint}}


def _error(error: EcoBuildError) -> dict:
    return {"ok": False, "result": None, "error": {"code": error.code, "message": error.message, "hint": error.hint}}


def _option(args: list[str], name: str) -> str:
    """args の --name の値（なければ空）。"""
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else ""


class Serve:
    """係の1回分の見回り（step）と、その状態（返答の終わりを見た時刻）。

    run(args, cwd, progress=None, stall=None)：ECOBuild のコマンドを cwd で実行し、その JSON の結果（{ok, result|error}）を
    返す。progress(line)：コマンドの経過（人向けの1行）。stall：経過がこの秒数出なければ止まったとみなして止める。
    emit(event)：起動した側への出来事（None なら起動した側はいない）。ack(key, timeout)：その返事を待つ（届いたか）。
    launch(root, role, resume, progress)：アプリ用の起動のしかた（app.Launch。AgentModule.app_launch。None なら
    アプリ用のエージェントを動かさない）。
    log(message)：したことを人に知らせる。

    見回りは待たない：頼みはすぐに受け取り（拾った印 .taken。頼んだ側は拾われたかで係がいるかを見る）、実行は裏で行う。
    同じ置き場所（作業空間）のものは届いた順に1つずつ、ほかの置き場所のものとは並べて（作業役を作る clone 等で長く
    かかっても、ほかのエージェントの頼みを待たせない）。ただし作業役の作成（agent team start）どうしは、同じ置き場所でも
    START_LIMIT まで並べる（進行役が何人も作るとき、1人ずつ待たせない）。作成とほかの頼みの順は変えない：ほかの頼み
    （close・restart 等）は前に届いた作成が終わってから、後に届いた作成はその頼みが終わってから（作っている途中の
    作業役を閉じない）。background=False なら、その場で実行する。"""

    def __init__(self, run: Run, *, emit: Callable[[dict], None] | None = None,
                 ack: Callable[[str, float], bool] = lambda key, timeout: True,
                 launch: Callable[..., app.Launch] | None = None,
                 log: Callable[[str], None] = lambda message: None, background: bool = True):
        self.run, self.emit, self.ack, self.log = run, emit, ack, log
        self.apps = app.Apps(launch, log) if launch is not None else None
        self.background = background
        self.started = time.time()
        self._replied: dict[Path, float] = {}
        self._queues: dict[Path, deque] = {}            # 置き場所 → まだ始めていない (並べてよいか, 仕事)
        self._running: dict[Path, list[bool]] = {}      # 置き場所 → 実行中の仕事の「並べてよいか」
        self._guard = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._progress: dict[Path, dict] = {}   # 拾って結果をまだ書いていない頼みの途中経過（ファイル → 中身）

    def step(self) -> None:
        self._beat()
        wake = self.apps.step() if self.apps is not None else []   # 前の係から引き継ぎ、終わったもの
        for folder in agent_status.folders():
            root = agent_status.workspace_of(folder)
            self._requests(folder, root)
            if root is not None:
                self._watch_reply(folder, root)
        for agent in wake:   # 返答の終わりを見てから起こす（起こすと置き場所を用意し直す）
            self._later(agent.folder, lambda agent=agent: self._wake(agent))

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

    def _later(self, folder: Path, job: Callable[[], None], *, parallel: bool = False) -> None:
        """job を裏で行う（置き場所 folder ごとに届いた順に1つずつ。ほかの置き場所とは並べて）。parallel：同じ置き場所の
        parallel の仕事どうしは、続けて届いたものを START_LIMIT まで並べる。"""
        if not self.background:
            self._do(job)
            return
        with self._guard:
            self._queues.setdefault(folder, deque()).append((parallel, job))
            self._next(folder)

    def _next(self, folder: Path) -> None:
        """置き場所 folder の、今始めてよい仕事を始める（_guard の中で。始めてから一覧に入れる：wait が取りこぼさない）。"""
        queue, running = self._queues[folder], self._running.setdefault(folder, [])
        while queue:
            parallel, job = queue[0]
            if running and not (parallel and all(running) and len(running) < START_LIMIT):
                return
            queue.popleft()
            running.append(parallel)
            thread = threading.Thread(target=self._finish, args=(folder, parallel, job), daemon=True)
            thread.start()
            self._threads.append(thread)

    def _finish(self, folder: Path, parallel: bool, job: Callable[[], None]) -> None:
        self._do(job)
        with self._guard:
            self._running[folder].remove(parallel)
            self._next(folder)

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
            request = agent_status.read(taken)
            starting = isinstance(request, dict) and [str(a) for a in request.get("args") or []][:3] == \
                ["agent", "team", "start"]
            self._later(folder, lambda taken=taken: self._answer(inbox, taken, root), parallel=starting)

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
        own = args[:2] in (["agent", "start"], ["agent", "stop"]) and (args[1] == "stop" or "--app" in args)
        if not own and (args[:2] != ["agent", "team"] or len(args) < 3 or args[2] not in TEAM_COMMANDS):
            return failed(f"この頼みは受け付けません：ecobuild {' '.join(args)}")
        if root is None:
            return failed("頼んだエージェントの作業空間が分かりません。", hint="エージェントを起動し直してください。")
        cwd = (root / str(request.get("cwd") or ".")).resolve()
        if not cwd.is_relative_to(root.resolve()):
            return failed("作業空間の外では実行しません。")
        shown = " ".join(a if len(a) <= 40 else a[:40] + "…" for a in args if a != "--json")
        self.log(f"頼み：ecobuild {shown}（{root}）")
        progress(f"実行しています：ecobuild {shown}")
        try:
            if own:
                return {"ok": True, "result": self._own(root, args, progress), "error": None}
            if args[2] in ("takeover", "handback") and len(args) > 3:
                member = team.find(root, args[3])
                return {"ok": True, "result": (self._takeover if args[2] == "takeover" else self._handback)(member, progress),
                        "error": None}
        except EcoBuildError as error:
            return _error(error)
        if args[2] in ("close", "restart") and len(args) > 3:
            try:
                member = team.find(root, args[3])
            except EcoBuildError as error:
                return _error(error)
            progress(f"「{member.name}」のエージェントを止めています…")
            self._stop(member.path)   # 使っているフォルダーは消せない・起動し直す前に止める
            if args[2] == "restart" and "--no-open" not in args:
                args = [*args, "--no-open"]   # 起動は係が（アプリ用で）
        doc = self.run(args, cwd, progress=progress, stall=team.STALL_SECONDS)
        if args[2] in ("start", "restart") and doc.get("ok") and (doc.get("result") or {}).get("path"):
            progress("エージェントを起動しています…")
            doc = {**doc, "result": self._start(doc["result"], progress)}
        return doc

    def _start(self, member: dict, progress: Callable[[str], None] = lambda line: None) -> dict:
        """作った（起動し直す）作業役を、係がアプリ用で起動する（AI が起動するものはタブにしない）。起動できなければ
        （コンテナでない等）、作業役はそのままで、わけを note に。"""
        if self.apps is None:
            return {**member, "note": "この係はエージェントを起動できません（起動していません）。"}
        resume = team.resumed_session(tuple(str(member.get("agent") or "").split()), lambda: "") or ""
        try:
            self.apps.start(Path(member["path"]), role=member.get("role", team.WORKER), prompt=member.get("prompt", ""),
                            resume=resume, progress=progress)
        except EcoBuildError as error:
            self.log(f"エージェントを起動できませんでした：{error.message}")
            return {**member, "note": f"作業役は作りましたが、起動していません：{error.message}"
                                      + (f"（{error.hint}）" if error.hint else "")}
        return {**member, "app": True}

    def _own(self, root: Path, args: list[str], progress: Callable[[str], None]) -> dict:
        """人が頼んだ、この作業空間のアプリ用の起動（agent start --app）・止める（agent stop）。"""
        if args[1] == "stop":
            if self.apps is None or not self.apps.holds(root):
                raise EcoBuildError(ErrorCode.AGENT_ERROR, "この作業空間のエージェントを、係は動かしていません。")
            self.apps.stop(root)
            return {"path": str(root), "stopped": True}
        if self.apps is None:
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "この係はアプリ用のエージェントを動かせません。")
        agent = self.apps.start(root, role=_option(args, "--role"), prompt=_option(args, "--prompt"), progress=progress)
        return {"path": str(root), "role": agent.role, "session": agent.session, "app": True}

    def _takeover(self, member: team.Member, progress: Callable[[str], None]) -> dict:
        """人が引き取る：係のアプリ用のエージェントを止め（返答を終えさせてから）、続きから開く会話を返す。"""
        if self.apps is not None and self.apps.holds(member.path):
            progress(f"「{member.name}」のエージェントを止めています（返答を終えてから）…")
            self.apps.stop(member.path)
        elif agent_status.running_mode(team.inbox_of(member.path)) == "":
            raise EcoBuildError(ErrorCode.AGENT_ERROR, f"「{member.name}」は、もう対話型（人の画面）で動いています。")
        session = agent_status.session_of(team.inbox_of(member.path))
        if not session:
            raise EcoBuildError(ErrorCode.AGENT_ERROR, f"「{member.name}」の会話が分かりません。")
        return {**_member(member), "session": session, "agent": f"claude --resume {session}"}

    def _handback(self, member: team.Member, progress: Callable[[str], None]) -> dict:
        """人が返す：対話型を閉じた後、係がアプリ用で続きから起こす。"""
        folder = team.inbox_of(member.path)
        if agent_status.running_mode(folder) == "":
            raise EcoBuildError(ErrorCode.AGENT_ERROR, f"「{member.name}」は、まだ対話型（人の画面）で動いています。",
                                hint="その画面（タブ）を閉じてから返してください。")
        session = agent_status.session_of(folder)
        if not session:
            raise EcoBuildError(ErrorCode.AGENT_ERROR, f"「{member.name}」の会話が分かりません。",
                                hint="agent team restart で新しい会話で起動し直せます。")
        if self.apps is None:
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "この係はアプリ用のエージェントを動かせません。")
        progress(f"「{member.name}」を係に戻しています…")
        self.apps.start(member.path, role=member.role, prompt=app.HANDBACK_PROMPT, resume=session, progress=progress)
        return {**_member(member), "session": session, "app": True}

    def _wake(self, agent: app.Agent) -> None:
        """前の係が持っていたものを、続きから起こす（返答の途中で止まっていたら続けさせる）。進行役に知らせる。"""
        interrupted = bool(agent.state.get("ended_working"))
        try:
            self.apps.start(agent.root, role=agent.role, resume=agent.session, progress=self.log,
                            prompt=app.INTERRUPTED_PROMPT if interrupted else "")
            done = "前の会話の続きから起こしました" + ("（返答の途中だったので、続けるよう伝えました）" if interrupted else "")
        except EcoBuildError as error:
            self.apps.stop(agent.root, 0)
            done = f"起こせませんでした：{error.message}"
        self.log(f"係が起動し直したので、{agent.root} のエージェントを{done}")
        info = team.member_info(agent.root)
        if info.get("lead"):
            name = f"{team.ROLE_NAMES.get(info.get('role'), '作業役')}「{info.get('name') or agent.root.name}」"
            agent_status.put(team.inbox_of(Path(info["lead"])), f"[ECOBuild] 係が起動し直したので、{name}を{done}。",
                             sender=str(agent.root), owner=team.notice_owner(agent.root))

    def wake(self) -> None:
        """係が動き始めたとき：前の係が持っていたアプリ用のエージェントを引き継ぐ（終わったものから続きから起こす）。"""
        if self.apps is not None:
            for agent in self.apps.adopt():
                self.log(f"前の係のエージェントを引き継ぎました（{agent.root}）")

    def close(self) -> None:
        """係が終わるとき：アプリ用のエージェントの標準入力を閉じる（返答を終えて終わる。次の係が続きから起こす）。"""
        if self.apps is not None:
            self.apps.close()

    def _stop(self, path: Path) -> None:
        """作業空間 path のエージェントを止める：係が持っていれば係が（返答を終えさせてから）、人の画面（対話型）なら
        起動した側に頼む（いなければ、動かしているプロセスを止める）。"""
        if self.apps is not None and self.apps.holds(path):
            self.apps.stop(path)
            return
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
            agent_status.put(team.inbox_of(lead), text, sender=str(root), owner=team.notice_owner(root))
            self.log(f"進行役に知らせました：{text.splitlines()[0]}")
        self.run(["project", "update"], root)   # 型に手元をそろえさせる（持たない型は not_supported。気にしない）


def _member(member: team.Member) -> dict:
    return {"name": member.name, "role": member.role, "path": str(member.path), "task": member.task,
            "branch": member.branch, "lead": member.lead}


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
