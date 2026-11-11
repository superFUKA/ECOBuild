"""ECOBuild の係（このPCで常駐する）：エージェントの間の取り次ぎを、画面を持つアプリから切り離して本体で行う。

- 頼み（children.REQUESTS）：エージェントの状態の置き場所に書かれた頼みを、このPCで実行して結果を書き戻す
  （children.forward が待っている）。拾ってから結果を書くまで、途中経過（children.PROGRESS）を毎秒書く。
  - ツール（{"tool", "arguments", "agent"}）：コンテナの中の MCP サーバーが渡す、子を扱うツール（children_*・
    report_to_parent）と、このPCで実行するツール（host_run。作業空間で ecobuild host <コマンド>。許したかは
    このPCの設定で確かめる）。呼び手は頼みを書いた置き場所のエージェント（頼みの agent と違えば断る）。
    確かめ（直接の子だけ・起動してよい登録・子の数）もここで行う。
  - 人の操作（{"args", "cwd"}）：係が持つエージェントの起動・止める・起動し直す・引き取る・返す・閉じる・言付けを届けに起こす
    （agent start --app --id・stop・restart・takeover・handback・close・wake〔agent send が頼む〕）。これはこのPCだけの置き場所
    （children.human_requests。コンテナにマウントしない）からだけ受ける：中のエージェントがまねて、ほかのエージェントを
    止める・閉じる等をさせない。
- 親への知らせ：子の返答が終わったら（replied.json）、親の受け箱に入れる（children.parent_notice。子タスクの子には、
  作業空間・GitHub を調べた事実と注意を添える：裏で行うので見回りは止まらない）。
- 返答が終わったら、作業空間の型に手元をそろえさせる（project update。C++ では Visual Studio の構成。ほかの型は何もしない）。
- AI が起動するエージェント（子）は、係がアプリ用の起動（画面なし。app）で持つ：起動し、閉じる・起動し直す前に止め、
  受け箱のものを標準入力へ入れる。係が終わるときは止め（返答を終えさせてから）、次の係が続きから起こす。

人が起動したもの（対話型）を動かしているのは、係を起動した側（GUI の窓等）。止める・開くは出来事（emit）としてその側に
頼む（返事 ack を待つ）：{"event": "agent-stop", "key", "id", "path"}・{"event": "agent-start", "key", "id", "parent",
"registration", "kind", "path", "prompt", "program"}。起動した側がいなければ、止めるのはそのプロセスを止める
（agent_status.running_pid）。

ECOBuild のコマンドは run で、作業空間の Module は find で開く（使う側が渡す：プログラム名・型を本体に書かない）。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from pathlib import Path

from ecobuild import settings as _settings
from ecobuild.errors import EcoBuildError

from . import agents, app, children, host, inside, registry
from . import status as agent_status
from .errors import ErrorCode

HUMAN_COMMANDS = ("start", "stop", "restart", "takeover", "handback", "close", "wake")   # 人の操作（agent <これ> <ID>）
LOCK = Path("agents") / "serve.lock"   # ECOBUILD_HOME の下：係はこのPCに1つ
STOP_TIMEOUT = 30                       # 起動した側に止めてもらう返事を待つ秒数
START_LIMIT = 4                         # 同じ置き場所の手伝いの起動を、並べて実行する数
_KEEP_HINT = ("子に提出・push してもらうか、要らなければ ecobuild workspace close \"{root}\" --discard-local で作業空間を"
              "消してから、もう一度閉じてください（agent close・children_close）。")   # 閉じる子の作業空間に GitHub にないもの

Run = Callable[..., dict]   # run(args, cwd, progress=None, stall=None)


def failed(message: str, hint: str | None = None) -> dict:
    return {"ok": False, "result": None, "error": {"code": ErrorCode.AGENT_ERROR, "message": message, "hint": hint}}


def _error(error: EcoBuildError) -> dict:
    return {"ok": False, "result": None, "error": {"code": error.code, "message": error.message, "hint": error.hint,
                                                   "details": error.details}}


def _option(args: list[str], name: str) -> str:
    """args の --name の値（なければ空）。"""
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else ""


def plain(value):
    """結果を JSON にできる形に（dataclass・Path・tuple。ほかのもの〔Repository 等〕は外す）。"""
    if is_dataclass(value) and not isinstance(value, type):
        found = {}
        for field in fields(value):
            item = plain(getattr(value, field.name))
            if not field.name.startswith("_") and item is not _SKIP:
                found[field.name] = item
        return found
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): item for key, raw in value.items() if (item := plain(raw)) is not _SKIP}
    if isinstance(value, (list, tuple)):
        return [item for raw in value if (item := plain(raw)) is not _SKIP]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "value") and isinstance(getattr(value, "value"), (str, int)):   # Enum
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _SKIP


_SKIP = object()


class Serve:
    """係の1回分の見回り（step）と、その状態（返答の終わりを見た時刻）。

    run(args, cwd, progress=None, stall=None)：ECOBuild のコマンドを cwd で実行し、その JSON の結果（{ok, result|error}）を
    返す。progress(line)：コマンドの経過（人向けの1行）。stall：経過がこの秒数出なければ止まったとみなして止める。
    emit(event)：起動した側への出来事（None なら起動した側はいない）。ack(key, timeout)：その返事を待つ（届いたか）。
    launch(agent_id, resume, progress)：記録のあるエージェントのアプリ用の起動のしかた（app.Launch。
    AgentModule.app_launch。None ならアプリ用のエージェントを動かさない）。
    find(path)：作業空間の Module（本体＋拡張。子タスクを作る・取り込む・作業空間を閉じる。None なら子タスクを扱わない）。
    log(message)：したことを人に知らせる。

    見回りは待たない：頼みはすぐに受け取り（拾った印 .taken。頼んだ側は拾われたかで係がいるかを見る）、実行は裏で行う。
    同じ置き場所（エージェント）のものは届いた順に1つずつ、ほかの置き場所のものとは並べて（子タスクを作る等で長く
    かかっても、ほかのエージェントの頼みを待たせない）。ただし手伝いの起動どうしは、同じ置き場所でも START_LIMIT まで
    並べる。background=False なら、その場で実行する。"""

    def __init__(self, run: Run, *, emit: Callable[[dict], None] | None = None,
                 ack: Callable[[str, float], bool] = lambda key, timeout: True,
                 launch: Callable[..., app.Launch] | None = None, find: Callable[[Path], object] | None = None,
                 log: Callable[[str], None] = lambda message: None, background: bool = True):
        self.run, self.emit, self.ack, self.log, self.find = run, emit, ack, log, find
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
            human = children.human_requests(folder.name)
            if root is not None:
                self._alive(folder / children.REQUESTS)
                self._alive(human)
            # 状態の置き場所（コンテナから書ける）からはツールの頼みだけ、人の操作はこのPCだけの置き場所から受ける
            self._requests(folder, root, folder / children.REQUESTS, human=False)
            self._requests(folder, root, human, human=True)
            if root is not None:
                self._watch_reply(folder)
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

    def _alive(self, inbox: Path) -> None:
        """頼みの置き場所 inbox に、係が動いている印（children.SERVE_BEAT）を書く（BEAT_EVERY 秒ごと。頼む側が先に係の
        生死を見る）。"""
        file = inbox / children.SERVE_BEAT
        seen = agent_status.read(file)
        if isinstance(seen, dict) and isinstance(seen.get("at"), (int, float)) \
                and time.time() - seen["at"] < children.BEAT_EVERY:
            return
        try:
            file.parent.mkdir(parents=True, exist_ok=True)
            agent_status._write(file, {"at": time.time(), "pid": os.getpid()})
        except OSError:
            pass

    def _beat(self) -> None:
        """実行中の頼みの途中経過に、係が動いている印（時刻）を書く。"""
        with self._guard:
            files = list(self._progress)
        for file in files:
            self._report(file)

    # ---- 頼み -------------------------------------------------------------------------------------------
    def _requests(self, folder: Path, root: Path | None, inbox: Path, *, human: bool) -> None:
        """inbox の頼みを拾う（folder：頼んだエージェントの状態の置き場所。仕事の順番もここごと）。human：人の操作を
        受けてよい置き場所（このPCだけのもの）か。"""
        for file in sorted(inbox.glob("*.json")) if inbox.is_dir() else ():
            if "." in file.stem:   # 頼みは <id>.json だけ（結果 <id>.result.json 等は拾わない）
                continue
            taken = file.with_suffix(".taken")
            try:
                os.replace(file, taken)       # 拾った（頼んだ側に係がいると分かる）。ほかが拾ったものは飛ばす
            except OSError:
                continue
            self._report(inbox / f"{file.stem}{children.PROGRESS}", "順番を待っています（同じエージェントの前の頼みを実行中）")
            request = agent_status.read(taken)
            helper = isinstance(request, dict) and request.get("tool") == "children_start" \
                and (request.get("arguments") or {}).get("kind") == children.HELPER
            self._later(folder, lambda taken=taken: self._answer(inbox, taken, folder, root, human=human),
                        parallel=helper)

    def _answer(self, inbox: Path, taken: Path, folder: Path, root: Path | None, *, human: bool = False) -> None:
        """拾った頼み1つを実行して、結果を書き戻す。"""
        request = agent_status.read(taken)
        report = inbox / f"{taken.stem}{children.PROGRESS}"
        if not isinstance(request, dict) or not request.get("id"):
            taken.unlink(missing_ok=True)
            self._report(report, done=True)
            return
        try:
            doc = self.handle(root, request, progress=lambda line: self._report(report, line), folder=folder,
                              human=human)
        except Exception as error:   # 頼んだ側を待たせたままにしない
            doc = failed(f"係が頼みを実行できませんでした：{error}")
        result = inbox / f"{request['id']}.result.json"
        temporary = result.with_name(result.name + ".tmp")
        try:
            inbox.mkdir(parents=True, exist_ok=True)   # 閉じたエージェントの頼み（agent close）：置き場所ごと消えている
            temporary.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, result)
        except OSError:
            pass   # 書けなければ、頼んだ側が待ちきれずに止まる
        taken.unlink(missing_ok=True)
        self._report(report, done=True)

    def handle(self, root: Path | None, request: dict, progress: Callable[[str], None] = lambda line: None, *,
               folder: Path | None = None, human: bool = True) -> dict:
        """頼み1つを実行して、結果の JSON（{ok, result|error}）を返す。progress：途中経過。folder：頼みを書いた
        エージェントの置き場所（ツールの呼び手）。human：人の操作（args）を受けてよいか（コンテナから書ける置き場所の
        頼みなら False：中のエージェントが人の操作をまねて、ほかのエージェントを止める・閉じる等をさせない）。"""
        if request.get("tool"):
            return self._tool(folder, request, progress)
        if not human:
            return failed("この置き場所からは、人の操作の頼みを受け付けません（ツールで頼んでください）。")
        args = [str(a) for a in request.get("args") or []]
        human = args[:1] == ["agent"] and len(args) > 1 and args[1] in HUMAN_COMMANDS \
            and (args[1] != "start" or "--app" in args)
        if not human:
            return failed(f"この頼みは受け付けません：ecobuild {' '.join(args)}")
        if root is None:
            return failed("頼んだエージェントの作業空間が分かりません。", hint="エージェントを起動し直してください。")
        shown = " ".join(a if len(a) <= 40 else a[:40] + "…" for a in args if a != "--json")
        self.log(f"頼み：ecobuild {shown}（{root}）")
        progress(f"実行しています：ecobuild {shown}")
        try:
            return {"ok": True, "result": self._human(root, args, progress), "error": None}
        except EcoBuildError as error:
            return _error(error)

    def _human(self, root: Path, args: list[str], progress: Callable[[str], None]) -> dict:
        """人の操作：記録のあるエージェント（この作業空間のもの）の起動（agent start --app --id <ID>）・止める・起動し直す・
        引き取る・返す・閉じる（agent <操作> <ID>）。"""
        action = args[1]
        agent_id = _option(args, "--id") if action == "start" else args[2] if len(args) > 2 else ""
        record = agents.load(agent_id)
        if os.path.normcase(str(Path(record.workspace).resolve())) != os.path.normcase(str(Path(root).resolve())):
            raise EcoBuildError(ErrorCode.AGENT_ERROR, f"エージェント {agent_id} は、この作業空間のものではありません。")
        if action == "stop":
            if self.apps is None or not self.apps.holds(agent_id):
                raise EcoBuildError(ErrorCode.AGENT_ERROR, f"エージェント {agent_id} を、係は動かしていません。")
            self.apps.stop(agent_id)
            return {"id": agent_id, "path": str(root), "stopped": True}
        if action == "restart":
            return self._restart(record, resume="--resume" in args, progress=progress)
        if action == "takeover":
            return self._takeover(record, progress, open_window="--no-open" not in args)
        if action == "handback":
            return self._handback(record, progress)
        if action == "close":
            return self._close(record, progress, force="--force" in args)
        if action == "wake":
            return {"id": agent_id, "path": str(root),
                    **self._wake_to_deliver(record, progress, later=f"agent restart {agent_id} --resume で起こすと届きます。")}
        if self.apps is None:
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "この係はアプリ用のエージェントを動かせません。")
        agent = self._launch(agent_id, record.folder, prompt=_option(args, "--prompt"), progress=progress)
        return {"id": agent_id, "path": str(root), "registration": agent.registration, "session": agent.session,
                "app": True}

    # ---- ツール（子を扱う） -------------------------------------------------------------------------------
    def _tool(self, folder: Path | None, request: dict, progress: Callable[[str], None]) -> dict:
        """エージェントの MCP サーバーからのツールの頼み。呼び手は頼みを書いた置き場所のエージェント。"""
        tool = str(request.get("tool") or "")
        try:
            caller = agents.load(folder.name) if folder is not None else None
            if caller is None or request.get("agent") != caller.id:   # 名乗りは必須（自分の置き場所から頼む）
                raise EcoBuildError(ErrorCode.AGENT_ERROR, "頼んだエージェントが分かりません（自分の置き場所から頼んでください）。")
            if not registry.allows_tool(children._registration(caller), tool):
                raise EcoBuildError(ErrorCode.AGENT_ERROR, f"ツール {tool} は、このエージェントの登録で許されていません。")
            if tool == host.TOOL:
                return {"ok": True, "result": self._host(caller, host.check_arguments(request.get("arguments") or {}),
                                                         progress), "error": None}
            arguments = children.check_arguments(tool, request.get("arguments") or {})
            self.log(f"ツール：{tool}（{caller.name}・{caller.id}）")
            return {"ok": True, "result": self._call(caller, tool, arguments, progress), "error": None}
        except EcoBuildError as error:
            return _error(error)

    def _call(self, caller: agents.AgentRecord, tool: str, arguments: dict, progress: Callable[[str], None]):
        if tool == "children_list":
            return {"id": caller.id, "members": children.listed(caller)}
        if tool == "children_start":
            return self._start_child(caller, arguments, progress)
        if tool == "report_to_parent":
            return children.report(caller, arguments["text"])
        child = children.child_of(caller, arguments["id"])
        if tool == "children_send":
            key = children.send(child, arguments["text"], sender=children.sender_of(caller))
            return {"id": child.id, "name": child.name, "message_id": key,
                    **self._wake_to_deliver(child, progress, later="children_restart で起こすと届きます。")}
        if tool == "children_cancel":
            return {"id": child.id, "name": child.name, "message_id": children.cancel(child, arguments["message"])}
        if tool == "children_stop":
            if not self._stop_agent(child, progress):
                raise EcoBuildError(ErrorCode.AGENT_ERROR, f"「{child.name}」は動いていません。")
            return {"id": child.id, "name": child.name, "stopped": True}
        if tool == "children_restart":
            return self._restart(child, resume=bool(arguments.get("resume")), progress=progress)
        if tool == "children_log":
            tail = arguments.get("tail")
            found, cursor = app.read_events(child.folder, tail=50 if tail is None else max(0, tail))
            return {"id": child.id, "name": child.name, "events": found, "next": cursor,
                    "activity": agent_status.activity(child.folder)}
        if tool == "children_accept":
            return self._accept(caller, child, progress)
        return self._close(child, progress)   # children_close

    def _host(self, caller: agents.AgentRecord, arguments: dict, progress: Callable[[str], None]) -> dict:
        """host_run：このPCで ecobuild host <コマンド> を実行し、その --json の結果を返す。許したかは、このPCの設定で
        もう一度確かめる（MCP サーバーの --host-run は中から変えられる）。"""
        root = Path(caller.workspace)
        if not inside.host_run(root):
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "この作業空間では、このPCでの実行を許していません。",
                                hint="人が ecobuild container set --host-run on で許し、エージェントを起動し直します。")
        args = host.argv(arguments)
        self.log(f"ツール：{host.TOOL}（{caller.name}・{caller.id}）：ecobuild {' '.join(args[:-1])}")
        return self.run(args, root, progress=progress)

    def _module(self, root: Path):
        if self.find is None:
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "この係は子タスクを扱えません。")
        return self.find(Path(root))

    def _start_child(self, caller: agents.AgentRecord, arguments: dict, progress: Callable[[str], None]) -> dict:
        """子を作り（children.start）、係がアプリ用で起動する。起動できなければ、子はそのままで、わけを note に。"""
        kind = arguments["kind"]
        module = self._module(caller.root) if kind == children.SUBTASK else None
        record, prompt = children.start(module, caller, registration=arguments["registration"], kind=kind,
                                        brief=arguments["brief"], title=arguments.get("title") or "", progress=progress)
        result = {**children.shown(record), "app": False}
        if self.apps is None:
            return {**result, "note": "この係はエージェントを起動できません（起動していません）。"}
        progress(f"「{record.name}」を起動しています…")
        try:
            self._launch(record.id, record.folder, prompt=prompt, progress=progress)
        except EcoBuildError as error:
            self.log(f"エージェントを起動できませんでした：{error.message}")
            return {**result, "note": f"子は作りましたが、起動していません：{error.message}"
                                      + (f"（{error.hint}）" if error.hint else "")}
        return {**children.shown(record), "app": True}

    def _restart(self, record: agents.AgentRecord, *, resume: bool, progress: Callable[[str], None]) -> dict:
        """止めて、係がアプリ用で起動し直す（作業空間・作業はそのまま。resume：前の会話の続きから）。"""
        prompt, session = children.restart_prompt(record, resume=resume)
        if self.apps is None:
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "この係はアプリ用のエージェントを動かせません。")
        self._stop_agent(record, progress)
        progress(f"「{record.name}」を起動し直しています…")
        self._launch(record.id, record.folder, prompt=prompt, resume=session, progress=progress)
        return {**children.shown(record), "app": True, "resumed": bool(session)}

    def _launch(self, agent_id: str, folder: Path, *, prompt: str = "", resume: str = "",
                progress: Callable[[str], None] = lambda line: None) -> app.Agent:
        """係がアプリ用で起動する。先に置き場所 folder へ起動中の印を書く（コンテナの用意で数十秒〜数分かかる間、様子を
        「止まっている」にしない：親が同じ仕事をもう一度任せないように）。起動が済めば印は消え（status.started）、
        失敗したら消す。"""
        agent_status.starting(folder)
        try:
            return self.apps.start(agent_id, prompt=prompt, resume=resume, progress=progress)
        except BaseException:
            agent_status.not_starting(folder)
            raise

    def _wake_to_deliver(self, record: agents.AgentRecord, progress: Callable[[str], None], *, later: str) -> dict:
        """言付けを入れた相手 record が止まっていれば、前の会話の続きから起こす（受け箱のものは、起こした後の見回りで
        標準入力へ届く。発言は足さない：言付けだけを読ませる）。結果に足すもの：woken（起こした）・note（起こせない・
        起こさないわけと、届け方 later）。動いている・起動中なら何もしない。タスクが閉じていれば起こさない（_wake と同じ）。
        人が起動したもの（親がいない）は人の画面で動かすものなので、係は起こさない。"""
        if self._agent_running(record):
            return {}
        if agent_status.activity(record.folder)["state"] == agent_status.STARTING:
            return {"note": f"「{record.name}」は起動中です。起動が済めば届きます。"}
        stopped = f"「{record.name}」は止まっているので、まだ届いていません"
        if not record.parent:
            return {"woken": False, "note": f"{stopped}（人が起動したエージェントです）。起動すると届きます。"}
        if self.apps is None:
            return {"woken": False, "note": f"{stopped}（この係は起こせません）。{later}"}
        if self._task_closed(record.root):
            return {"woken": False, "note": f"{stopped}（タスクが閉じているので起こしませんでした）。{later}"}
        try:
            _, session = children.restart_prompt(record, resume=True)
            progress(f"「{record.name}」が止まっているので、続きから起こして届けます…")
            self._launch(record.id, record.folder, resume=session, progress=progress)
        except EcoBuildError as error:
            self.log(f"言付けを届けるために起こせませんでした（{record.id}）：{error.message}")
            return {"woken": False, "note": f"{stopped}（起こせませんでした：{error.message}）。{later}"}
        return {"woken": True, "note": f"「{record.name}」が止まっていたので、前の会話の続きから起こしました（言付けはすぐ届きます）。"}

    def _accept(self, caller: agents.AgentRecord, child: agents.AgentRecord, progress: Callable[[str], None]) -> dict:
        """子タスクの提出を取り込む：確かめ（閉じられないときは何もしない）→ 子を止めて控えを写す → task finish →
        sync → 作業空間を閉じる（finish が消していなければ）→ 記録を消す。task finish で止まったら何も閉じない。
        取り込めた後は、sync・作業空間を閉じるのが済まなくても記録を消し、済まなかったものとそのわけを note に書く。"""
        if caller.kind == agents.HELPER:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "手伝いは子タスクを取り込めません（タスクの持ち主がすることです）。")
        if not children.own_workspace(child) or not child.task:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"「{child.name}」は手伝いなので、取り込む提出はありません。",
                                hint="終わったら children_close で閉じてください。")
        problems = children.close_problems(child)
        if problems:
            raise EcoBuildError(ErrorCode.UNFINISHED_WORK, f"「{child.name}」はまだ取り込めません（閉じられないため）。",
                                hint="様子を確かめて（children_list）、終わるのを待つか止めてから、もう一度。", details=problems)
        module = self._module(caller.root)
        number = int(child.task.get("number") or 0)
        try:
            self._stop_agent(child, progress)
            children.stop_container(child.root, progress)   # 動いたままだと WSL・メモリーを使い続ける
            kept = children.archive(child)
            progress(f"#{number}（{child.name}）を取り込みます…")
            finished = plain(module.finish(number))
        except EcoBuildError as error:
            raise EcoBuildError(error.code, f"「{child.name}」の取り込みが task finish で止まりました：{error.message}",
                                hint=error.hint, details=error.details) from error
        # 取り込めた後は、子の記録を必ず閉じる（残すと親が先へ進めない）。済まなかったものは note に
        notes = []
        synced = closed = None
        try:
            progress("手元を最新にします…")
            synced = plain(module.sync())
        except EcoBuildError as error:
            notes.append(f"手元を最新にできませんでした（sync）：{error.message}" + (f"（{error.hint}）" if error.hint else ""))
        if child.root.exists():
            try:
                closed = plain(type(module).close_workspace(child.root))
            except EcoBuildError as error:
                left = "・".join(map(str, error.details)) if isinstance(error.details, (list, tuple)) else ""
                notes.append(f"子の作業空間 {child.root} は閉じられなかったので残しました：{error.message}"
                             + (f"（{left}）" if left else "") + "。"
                             + (f"要らなければ ecobuild workspace close \"{child.root}\" --discard-local で消せます。"
                                if error.code == ErrorCode.UNFINISHED_WORK else error.hint or ""))
        children.forget(child)
        return {"id": child.id, "name": child.name, "task": number, "finish": finished, "sync": synced,
                "closed": closed, "archive": kept, **({"note": "／".join(notes)} if notes else {})}

    def _close(self, record: agents.AgentRecord, progress: Callable[[str], None], *, force: bool = False) -> dict:
        """閉じる：止めて、控えを親の作業空間へ写し、子タスクの作業空間なら場所ごと消し、記録を消す。閉じられないわけ
        （作業中・届いていない言付け・提出の後のコミット・子がいる。force なら子がいること以外は飛ばす）・GitHub にない
        もの（未コミットの変更・push していないコミット）があれば何もしない。"""
        problems = children.close_problems(record)
        if force:
            problems = [p for p in problems if "子がいます" in p]
        if problems:
            raise EcoBuildError(ErrorCode.UNFINISHED_WORK, f"「{record.name}」はまだ閉じられません。",
                                hint="様子を確かめて、終わるのを待つか止めてから、もう一度。", details=problems)
        own = children.own_workspace(record) and record.root.exists()
        if own:
            left = children.unpushed_files(record)
            if left:
                raise EcoBuildError(ErrorCode.UNFINISHED_WORK, f"「{record.name}」の作業空間に、GitHub にない変更があります。",
                                    hint=_KEEP_HINT.format(root=record.root),
                                    details=[f"ファイル：{path}" for path in left])
        self._stop_agent(record, progress)
        kept = children.archive(record)
        result = None
        if own:
            children.stop_container(record.root, progress)   # 動いたままだと WSL・メモリーを使い続ける
            progress(f"「{record.name}」の作業空間を閉じています…")
            module = self._module(record.root)
            try:
                result = plain(type(module).close_workspace(record.root))
            except EcoBuildError as error:   # workspace close 向けの案内（--discard-local を付ける）は、ここでは使えない
                if error.code != ErrorCode.UNFINISHED_WORK:
                    raise
                raise EcoBuildError(error.code, f"「{record.name}」の作業空間に、GitHub にないものがあります。",
                                    hint=_KEEP_HINT.format(root=record.root), details=error.details) from error
        children.forget(record)
        if not own and not any(self._agent_running(other) for other in agents.in_workspace(record.root)):
            # 作業空間の最後のエージェントを閉じた：コンテナを止める（動いたままだと WSL・メモリーを使い続ける）
            children.stop_container(record.root, progress)
        return {"id": record.id, "name": record.name, "path": record.workspace, "workspace": result, "archive": kept}

    def _agent_running(self, record: agents.AgentRecord) -> bool:
        """エージェントが動いているか（係が持っている・動かしているプロセスがある）。"""
        if self.apps is not None and self.apps.holds(record.id):
            return True
        folder = agent_status.directory(record.id)
        return folder is not None and agent_status.running_pid(folder) is not None

    # ---- 止める・引き取る ------------------------------------------------------------------------------------
    def _stop_agent(self, record: agents.AgentRecord, progress: Callable[[str], None] = lambda line: None) -> bool:
        """エージェントを止める：係が持っていれば係が（返答を終えさせてから）、人の画面（対話型）なら起動した側に頼む
        （いなければ、動かしているプロセスを止める）。動いていたか。"""
        if self.apps is not None and self.apps.holds(record.id):
            progress(f"「{record.name}」を止めています（返答を終えてから）…")
            self.apps.stop(record.id)
            return True
        folder = agent_status.directory(record.id)
        pid = agent_status.running_pid(folder) if folder is not None else None
        if pid is None:
            return False
        progress(f"「{record.name}」を止めています…")
        if self.emit is None:
            agent_status.stop(pid)
            return True
        key = uuid.uuid4().hex
        self.emit({"event": "agent-stop", "key": key, "id": record.id, "path": record.workspace})
        if not self.ack(key, STOP_TIMEOUT):
            self.log(f"エージェントを止めた返事が届きませんでした（{record.id}）。プロセスを止めます。")
            agent_status.stop(pid)
        return True

    def _takeover(self, record: agents.AgentRecord, progress: Callable[[str], None], *, open_window: bool) -> dict:
        """人が引き取る：係のアプリ用のエージェントを止め（返答を終えさせてから）、続きから開く会話を返す。open_window で
        起動した側（GUI）がいれば、人の画面で開くよう頼む（agent-start。opened）。"""
        folder = record.folder
        if self.apps is not None and self.apps.holds(record.id):
            progress(f"「{record.name}」のエージェントを止めています（返答を終えてから）…")
            self.apps.stop(record.id)
        elif agent_status.running_mode(folder) == "":
            raise EcoBuildError(ErrorCode.AGENT_ERROR, f"「{record.name}」は、もう対話型（人の画面）で動いています。")
        session = agent_status.session_of(folder) or record.session
        if not session:
            raise EcoBuildError(ErrorCode.AGENT_ERROR, f"「{record.name}」の会話が分かりません。")
        program = f"claude --resume {session}"
        result = {**children.shown(record), "session": session, "agent": program, "opened": False}
        if open_window and self.emit is not None:
            key = uuid.uuid4().hex
            self.emit({"event": "agent-start", "key": key, "id": record.id, "parent": record.parent,
                       "registration": record.registration, "kind": record.kind, "path": record.workspace,
                       "prompt": "", "program": program})
            result["opened"] = self.ack(key, STOP_TIMEOUT)
        return result

    def _handback(self, record: agents.AgentRecord, progress: Callable[[str], None]) -> dict:
        """人が返す：対話型を閉じた後、係がアプリ用で続きから起こす。"""
        folder = record.folder
        if agent_status.running_mode(folder) == "":
            raise EcoBuildError(ErrorCode.AGENT_ERROR, f"「{record.name}」は、まだ対話型（人の画面）で動いています。",
                                hint="その画面（タブ）を閉じてから返してください。")
        session = agent_status.session_of(folder) or record.session
        if not session:
            raise EcoBuildError(ErrorCode.AGENT_ERROR, f"「{record.name}」の会話が分かりません。",
                                hint="agent restart で新しい会話で起動し直せます。")
        if self.apps is None:
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "この係はアプリ用のエージェントを動かせません。")
        progress(f"「{record.name}」を係に戻しています…")
        self._launch(record.id, record.folder, prompt=app.HANDBACK_PROMPT, resume=session, progress=progress)
        return {**children.shown(record), "session": session, "app": True}

    def _wake(self, agent: app.Agent) -> None:
        """前の係が持っていたものを、続きから起こす（返答の途中で止まっていたら続けさせる）。親に知らせる。
        タスクが閉じていれば起こさず、持つのをやめる（閉じ忘れた子が起き上がり、コンテナが動き続けないように）。"""
        interrupted = bool(agent.state.get("ended_working"))
        if self._task_closed(agent.root):
            self.apps.stop(agent.agent_id, 0)
            done = "起こしませんでした（タスクが閉じています。children_close・agent close で閉じられます）"
        else:
            try:
                self._launch(agent.agent_id, agent.folder, resume=agent.session, progress=self.log,
                             prompt=app.INTERRUPTED_PROMPT if interrupted else "")
                done = "前の会話の続きから起こしました" + ("（返答の途中だったので、続けるよう伝えました）" if interrupted else "")
            except EcoBuildError as error:
                self.apps.stop(agent.agent_id, 0)
                done = f"起こせませんでした：{error.message}"
        self.log(f"係が起動し直したので、{agent.root} のエージェント {agent.agent_id} を{done}")
        record = children._load_or_none(agent.agent_id)
        parent = children._load_or_none(record.parent) if record is not None else None
        if parent is not None:
            agent_status.put(parent.folder, f"[ECOBuild] 係が起動し直したので、{children._who(record)}を{done}。",
                             sender=record.id)

    def _task_closed(self, root: Path) -> bool:
        """作業空間 root のタスクが閉じているか（GitHub に聞く。分からなければ閉じていないとみなす＝起こす）。"""
        try:
            doc = self.run(["task", "status", "--json"], root)
        except Exception:
            return False
        result = doc.get("result") if isinstance(doc, dict) and doc.get("ok") else None
        return isinstance(result, dict) and result.get("state") == "closed"

    def wake(self) -> None:
        """係が動き始めたとき：前の係が持っていたアプリ用のエージェントを引き継ぐ（終わったものから続きから起こす）。"""
        if self.apps is not None:
            for agent in self.apps.adopt():
                self.log(f"前の係のエージェントを引き継ぎました（{agent.root}）")

    def close(self) -> None:
        """係が終わるとき：アプリ用のエージェントの標準入力を閉じる（返答を終えて終わる。次の係が続きから起こす）。"""
        if self.apps is not None:
            self.apps.close()

    # ---- 返答の終わり ----------------------------------------------------------------------------------------
    def _watch_reply(self, folder: Path) -> None:
        replied = agent_status.read(folder / "replied.json")
        at = replied.get("at") if isinstance(replied, dict) else None
        if not isinstance(at, (int, float)):
            return
        before = self._replied.get(folder)
        self._replied[folder] = at
        if at == before or (before is None and at < self.started):   # 見た・係が動く前のもの
            return
        message = replied.get("message") or ""
        continued = replied.get("continued") if isinstance(replied.get("continued"), int) else 0
        self._later(folder, lambda: self.replied(folder, message, continued=continued))

    def replied(self, folder: Path, message: str, *, continued: int = 0) -> None:
        """置き場所 folder のエージェントの返答が終わった（continued：受け箱の言付けを受け取って、返答を終えずに続けて
        いる）。親の受け箱にまだ届いていない、この子の前の知らせは出して、新しい知らせにまとめる（最新の1件だけ渡す）。"""
        record = children._load_or_none(Path(folder).name)
        if record is None:
            return
        parent = children._load_or_none(record.parent)
        if parent is not None:
            pending = agent_status.forget_from(parent.folder, record.id, agent_status.NOTICE, remove=False)
            notice = children.parent_notice(record, message, continued=continued, merged=pending)
            if notice is not None:
                _, text = notice
                agent_status.forget_from(parent.folder, record.id, agent_status.NOTICE)   # 知らせを作れてから出す
                agent_status.put(parent.folder, text, sender=record.id, kind=agent_status.NOTICE)
                self.log(f"親に知らせました：{text.splitlines()[0]}")
        if not continued:
            self.run(["project", "update"], record.root)   # 型に手元をそろえさせる（持たない型は not_supported。気にしない）


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
