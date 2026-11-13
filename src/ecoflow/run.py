"""流れの実行：状態の保存（原子的な書き込み・ロック）と状態機械（順番・判定・差し戻し・繰り返し・待ち・再開）。

実行は1つのフォルダー（<置き場所>/<実行の id>/）：
- state.json：{flow, definition（実行を作ったときの定義の写し）, inputs, vars, status, current,
  steps: {id: {status, attempts, retried, backs, loops, message, out, prev_message, prev_out, started, ended, data}},
  history: [出来事]}。一時ファイルに書いてから置き換える。読むときに形を確かめる（壊れていれば RUN_BROKEN）。
- lock・held：OS のファイルロック（動かしているプロセスが両方を持つ。プロセスが終われば OS が外す）。操作どうしの
  取り合いは lock、「動いているか」を見る（status 等）のは held だけを試す（見るだけで操作の取り合いに割り込まない）。
  owner.json：持ち主の pid（表示用）。
- cancel：止めてほしい印（動かしているプロセスが、工程の区切りで見る。種類も ctx.cancelled() で見られる）。止まる側が
  終わり・失敗・待ちに移るときと、ロックを取って操作を始めるときに消す（残った印で後の操作を止めない）。
- <工程>.log：工程ごとのログ（種類が書く）。
置き場所は、工程（エージェント等）が書き換えられない所に置く（利用側が決める）。

工程の状態：pending・running・done・failed・waiting・skipped・cancelled。実行の状態：running・waiting・done・failed・
cancelled（running なのにロックの持ち主がいなければ、表示は interrupted＝中断）。
工程を始める・飛ばす・待ちに戻すときは、前の回の message・out を prev_message・prev_out に移して空にする。
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import template as _expand
from .definition import Flow, Outcome, Step, as_kind, load
from .errors import ErrorCode, FlowError

PENDING, RUNNING, DONE, FAILED, WAITING, SKIPPED, CANCELLED = (
    "pending", "running", "done", "failed", "waiting", "skipped", "cancelled")
INTERRUPTED = "interrupted"   # 表示だけ：running なのに動かしているプロセスがいない
OUTCOMES = (DONE, FAILED, WAITING)
RUN_STATES = (RUNNING, WAITING, DONE, FAILED, CANCELLED)
STEP_STATES = (PENDING, RUNNING, DONE, FAILED, WAITING, SKIPPED, CANCELLED)
STATE_FILE = "state.json"
LOCK_FILE = "lock"
HELD_FILE = "held"
LOCK_TRIES = 10       # ロックを取り直す回数（間 LOCK_PAUSE 秒。ほかが一瞬持っているだけなら待つ）
LOCK_PAUSE = 0.05
OWNER_FILE = "owner.json"
CANCEL_FILE = "cancel"
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
NAMES = {PENDING: "待ち", RUNNING: "実行中", DONE: "済み", FAILED: "失敗", WAITING: "人の答え待ち", SKIPPED: "飛ばした",
         CANCELLED: "取り消し", INTERRUPTED: "中断"}


def _read(path: Path):
    """JSON を読む（ない・読めなければ None。書き換えの最中に当たったときのために、少しだけ読み直す）。"""
    for attempt in range(3):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            if attempt == 2:
                return None
            time.sleep(0.05)
    return None


def _write(path: Path, value) -> None:
    """一時ファイルに書いてから置き換える（読む側が書きかけを見ない）。"""
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:   # Windows：読んでいる最中は置き換えられない
            if attempt == 19:
                raise
            time.sleep(0.05)


def valid_id(run_id: str) -> bool:
    return bool(run_id) and RUN_ID.match(run_id) is not None and ".." not in run_id


def _broken(folder: Path, why: str) -> FlowError:
    return FlowError(ErrorCode.RUN_BROKEN, f"実行 {Path(folder).name} の記録（{STATE_FILE}）が壊れています：{why}",
                     details={"folder": str(folder)})


def check_state(state, folder: Path) -> dict:
    """state.json の形を確かめる（壊れていれば RUN_BROKEN）。"""
    if not isinstance(state, dict):
        raise _broken(folder, "読めません")
    for key, kind in (("id", str), ("flow", str), ("status", str), ("definition", dict), ("inputs", dict),
                      ("vars", dict), ("steps", dict), ("history", list)):
        if not isinstance(state.get(key), kind):
            raise _broken(folder, f"{key} がないか、形が違います")
    if state["status"] not in RUN_STATES:
        raise _broken(folder, f"状態「{state['status']}」を知りません")
    current = state.get("current")
    if current is not None and current not in state["steps"]:
        raise _broken(folder, f"今の工程「{current}」がありません")
    for key, entry in state["steps"].items():
        if not isinstance(entry, dict) or entry.get("status") not in STEP_STATES or not isinstance(entry.get("out", {}), dict):
            raise _broken(folder, f"工程 {key} の記録の形が違います")
    return state


class Run:
    """1つの実行（フォルダーと state.json）。"""

    def __init__(self, folder: Path, state: dict):
        self.folder = Path(folder)
        self.state = state

    @classmethod
    def load(cls, folder: Path) -> "Run":
        return cls(folder, check_state(_read(Path(folder) / STATE_FILE), Path(folder)))

    def reload(self) -> None:
        self.state = Run.load(self.folder).state

    @property
    def id(self) -> str:
        return self.state["id"]

    @property
    def flow(self) -> str:
        return self.state["flow"]

    @property
    def status(self) -> str:
        return self.state["status"]

    @property
    def steps(self) -> dict:
        return self.state["steps"]

    @property
    def vars(self) -> dict:
        return self.state["vars"]

    @property
    def shown_status(self) -> str:
        """表示の状態（running なのに動かしているプロセスがいなければ interrupted）。"""
        return INTERRUPTED if self.status == RUNNING and not self.locked() else self.status

    def locked(self) -> bool:
        """動かしているプロセスがいるか（held を取れるかを試す。lock には触らない）。"""
        path = self.folder / HELD_FILE
        if not path.exists():
            return False
        try:
            with open(path, "a+") as file:
                if not _try_lock(file):
                    return True
                _unlock(file)
        except OSError:
            return True
        return False

    def owner(self) -> int | None:
        owner = _read(self.folder / OWNER_FILE)
        return owner.get("pid") if isinstance(owner, dict) and isinstance(owner.get("pid"), int) else None

    def cancel_requested(self) -> bool:
        return (self.folder / CANCEL_FILE).exists()

    def forget_cancel(self) -> None:
        (self.folder / CANCEL_FILE).unlink(missing_ok=True)

    def save(self, clock: Callable[[], float] = time.time) -> None:
        self.state["updated"] = clock()
        _write(self.folder / STATE_FILE, self.state)

    def event(self, kind: str, step: str | None = None, message: str = "", clock: Callable[[], float] = time.time) -> None:
        self.state["history"].append({"at": clock(), "event": kind, "step": step, "message": message})

    def log_path(self, step_id: str) -> Path:
        return self.folder / f"{step_id}.log"

    def log(self, step_id: str, text: str) -> None:
        with open(self.log_path(step_id), "a", encoding="utf-8") as file:
            file.write(text if text.endswith("\n") else text + "\n")

    def scope(self, step_id: str | None = None) -> dict:
        """展開・条件の名前：inputs・vars・steps・out（その工程の）・run。"""
        steps = {key: {"status": value.get("status"), "message": value.get("message", ""), "out": value.get("out") or {},
                       "prev_message": value.get("prev_message", ""), "prev_out": value.get("prev_out") or {},
                       "attempts": value.get("attempts", 0)} for key, value in self.steps.items()}
        out = steps[step_id]["out"] if step_id in steps else {}
        return {"inputs": dict(self.state.get("inputs") or {}), "vars": dict(self.vars), "steps": steps, "out": out,
                "run": {"id": self.id, "dir": self.state.get("dir", ""), "flow": self.flow}}

    def summary(self) -> dict:
        """表示・JSON 用の形。"""
        definition = self.state.get("definition") or {}
        types = {s.get("id"): s.get("type") for s in definition.get("steps") or () if isinstance(s, Mapping)}
        return {"id": self.id, "flow": self.flow, "status": self.shown_status, "current": self.state.get("current"),
                "dir": self.state.get("dir", ""), "folder": str(self.folder), "created": self.state.get("created"),
                "updated": self.state.get("updated"), "inputs": self.state.get("inputs") or {}, "vars": dict(self.vars),
                "cancel_requested": self.cancel_requested(),
                "steps": [{"id": key, "type": types.get(key, ""), "status": value.get("status"),
                           "attempts": value.get("attempts", 0), "retried": value.get("retried", 0),
                           "backs": value.get("backs", 0), "loops": value.get("loops", 0),
                           "message": value.get("message", ""), "out": value.get("out") or {},
                           "started": value.get("started"), "ended": value.get("ended"),
                           "log": str(self.log_path(key)) if self.log_path(key).is_file() else None}
                          for key, value in self.steps.items()],
                "history": list(self.state.get("history") or ())}


def _try_lock(file) -> bool:
    """開いたファイルの排他ロックを、待たずに取る（取れたら True）。"""
    try:
        if os.name == "nt":
            import msvcrt
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(file) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _take(path: Path, tries: int):
    """path のロックを、短く取り直しながら取る（取れたら開いたファイル、取れなければ None）。"""
    file = open(path, "a+")
    for attempt in range(tries):
        if _try_lock(file):
            return file
        if attempt + 1 < tries:
            time.sleep(LOCK_PAUSE)
    file.close()
    return None


@contextmanager
def lock(run: Run, *, tries: int = LOCK_TRIES) -> Iterator[None]:
    """実行のロック（OS のファイルロック。lock と held）を持つ間だけ、中を実行する。ほかが持っていれば RUN_LOCKED。"""
    first = _take(run.folder / LOCK_FILE, tries)
    held = None
    if first is not None:
        try:
            held = _take(run.folder / HELD_FILE, LOCK_TRIES * 4)   # held は見る側が一瞬持つだけ
        except OSError:
            held = None
    if held is None:
        if first is not None:
            _unlock(first)
            first.close()
        pid = run.owner()
        raise FlowError(ErrorCode.RUN_LOCKED,
                        f"実行 {run.id} は、ほかのプロセス{f'（pid {pid}）' if pid else ''}が動かしています。",
                        details={"pid": pid})
    try:
        _write(run.folder / OWNER_FILE, {"pid": os.getpid(), "at": time.time()})
        yield
    finally:
        try:
            (run.folder / OWNER_FILE).unlink(missing_ok=True)
        except OSError:
            pass
        for file in (held, first):
            _unlock(file)
            file.close()


def inputs_for(flow: Flow, values: Mapping[str, Any]) -> dict:
    """実行の入力：渡したもの＋既定。ない名前・足りない入力は INVALID_INPUT。"""
    known = {i.name: i for i in flow.inputs}
    unknown = sorted(set(values) - set(known))
    if unknown:
        raise FlowError(ErrorCode.INVALID_INPUT, f"流れ {flow.name} に入力 {', '.join(unknown)} はありません。",
                        details={"known": sorted(known)})
    result = {name: item.default for name, item in known.items() if item.default is not None}
    result.update(values)
    missing = [name for name, item in known.items() if item.required and _expand.text_of(result.get(name)) == ""]
    if missing:
        raise FlowError(ErrorCode.INVALID_INPUT, f"流れ {flow.name} の入力 {', '.join(missing)} がありません。",
                        details={"missing": missing})
    return result


class Store:
    """実行の置き場所（<folder>/<実行の id>/）。display：${run.dir} に出す書き方（実行のフォルダー → 文。既定はそのパス）。"""

    def __init__(self, folder: Path, *, display: Callable[[Path], str] = str, clock: Callable[[], float] = time.time):
        self.folder = Path(folder)
        self.display = display
        self.clock = clock

    def _new_folder(self, name: str, run_id: str | None) -> Path:
        """実行のフォルダーを作る（同じ秒に重なれば -2・-3 …）。run_id を渡せばその名前（あれば誤り）。"""
        self.folder.mkdir(parents=True, exist_ok=True)
        if run_id is not None:
            if not valid_id(run_id):
                raise FlowError(ErrorCode.INVALID_INPUT, f"実行の名前「{run_id}」は使えません。")
            folder = self.folder / run_id
            folder.mkdir()
            return folder
        base = f"{name}-{time.strftime('%Y%m%d-%H%M%S', time.localtime(self.clock()))}"
        for number in range(1, 1000):
            folder = self.folder / (base if number == 1 else f"{base}-{number}")
            try:
                folder.mkdir()
                return folder
            except FileExistsError:
                continue
        raise FlowError(ErrorCode.INVALID_INPUT, f"実行の名前を決められません（{base}）。")

    def create(self, flow: Flow, values: Mapping[str, Any] | None = None, run_id: str | None = None) -> Run:
        inputs = inputs_for(flow, values or {})
        folder = self._new_folder(flow.name, run_id)
        now = self.clock()
        state = {"version": 1, "id": folder.name, "flow": flow.name, "definition": flow.data, "inputs": inputs,
                 "vars": {}, "status": RUNNING, "current": flow.steps[0].id, "dir": self.display(folder),
                 "created": now, "updated": now, "history": [],
                 "steps": {s.id: {"status": PENDING, "attempts": 0, "retried": 0, "backs": 0, "loops": 0, "message": "",
                                  "out": {}, "started": None, "ended": None, "data": {}} for s in flow.steps}}
        run = Run(folder, state)
        run.event("created", clock=self.clock)
        run.save(self.clock)
        return run

    def get(self, run_id: str) -> Run:
        if not valid_id(run_id) or not (self.folder / run_id / STATE_FILE).is_file():
            raise FlowError(ErrorCode.RUN_NOT_FOUND, f"実行 {run_id} はありません。")
        return Run.load(self.folder / run_id)

    def runs(self) -> list[Run]:
        """実行（作った順）。壊れたものは除く。"""
        found = []
        for folder in sorted(self.folder.glob("*")) if self.folder.is_dir() else ():
            if (folder / STATE_FILE).is_file():
                try:
                    found.append(Run.load(folder))
                except FlowError:
                    continue
        return sorted(found, key=lambda r: (r.state.get("created") or 0, r.id))

    def latest(self) -> Run | None:
        runs = self.runs()
        return runs[-1] if runs else None


class Context:
    """工程の種類に渡すもの：展開・ログ・進み具合・止めてほしいか・工程の覚え書き（data。再開のときに残っている）。"""

    def __init__(self, engine: "Engine", run: Run, step: Step, resumed: bool):
        self._engine = engine
        self.run = run
        self.step = step
        self.resumed = resumed   # 中断した工程の続き（data に前の覚え書きがある）

    @property
    def run_id(self) -> str:
        return self.run.id

    @property
    def folder(self) -> Path:
        """実行の状態のフォルダー（工程からは書き換えさせない所）。"""
        return self.run.folder

    @property
    def dir(self) -> str:
        """${run.dir}（利用側が決めた書き方）。"""
        return self.run.state.get("dir", "")

    @property
    def attempt(self) -> int:
        return self.run.steps[self.step.id].get("attempts", 0)

    @property
    def timeout(self) -> float | None:
        return self.step.timeout

    @property
    def data(self) -> dict:
        """工程の覚え書き（save で残す。新しく始めた工程では空）。"""
        return self.run.steps[self.step.id].setdefault("data", {})

    @property
    def scope(self) -> dict:
        return self.run.scope(self.step.id)

    def save(self) -> None:
        self.run.save(self._engine.clock)

    def expand(self, text: str) -> str:
        return _expand.expand(text, self.scope)

    def setting(self, name: str, default: Any = None) -> Any:
        """種類の設定（展開したもの）。"""
        return _expand.expand_value(self.step.settings.get(name, default), self.scope)

    def progress(self, message: str) -> None:
        self._engine.say(message)

    def log(self, text: str) -> None:
        self.run.log(self.step.id, text)

    @property
    def log_path(self) -> Path:
        return self.run.log_path(self.step.id)

    def cancelled(self) -> bool:
        return self.run.cancel_requested()


def _forget(entry: dict) -> None:
    """前の回の message・out を prev_message・prev_out に移して空にする（古い値を今の値として読ませない）。"""
    if entry.get("message") or entry.get("out"):
        entry["prev_message"], entry["prev_out"] = entry.get("message", ""), entry.get("out") or {}
    entry.update(message="", out={})


class Engine:
    """状態機械。kinds：種類の名前 → Kind か関数(step, ctx) → Outcome。progress：進み具合の文。"""

    def __init__(self, kinds: Mapping, *, progress: Callable[[str], None] | None = None,
                 clock: Callable[[], float] = time.time):
        self.kinds = {name: as_kind(kind) for name, kind in kinds.items()}
        self.progress = progress
        self.clock = clock

    def say(self, message: str) -> None:
        if self.progress is not None:
            self.progress(message)

    def definition(self, run: Run) -> Flow:
        """実行を作ったときの定義の写し（今の種類で確かめる）。工程の記録と合わなければ RUN_BROKEN。"""
        try:   # 種類を見ずに読めなければ記録が壊れている。種類がないだけなら定義の誤り（INVALID_FLOW）
            load(run.state.get("definition") or {}, run.flow)
        except FlowError as error:
            raise _broken(run.folder, f"定義の写しが読めません（{error.message}）") from error
        flow = load(run.state.get("definition") or {}, run.flow, self.kinds)
        missing = [s.id for s in flow.steps if s.id not in run.steps]
        if missing:
            raise _broken(run.folder, f"工程 {', '.join(missing)} の記録がありません")
        return flow

    # ---- 操作 -------------------------------------------------------------------------------------------
    def start(self, store: Store, flow: Flow, values: Mapping[str, Any] | None = None, run_id: str | None = None) -> Run:
        """実行を作り、待ち・終わり・失敗まで進める。"""
        run = store.create(flow, values, run_id)
        self.say(f"実行 {run.id} を始めます（{len(flow.steps)} 工程）")
        with lock(run):
            self._advance(run, flow)
        return run

    @contextmanager
    def _operating(self, run: Run, allowed: tuple[str, ...]) -> Iterator[None]:
        """ロックを取り、読み直して状態を確かめる。ロックを取れたなら、残っている取り消しの印は古いもの（消す）。"""
        with lock(run):
            run.reload()
            run.forget_cancel()
            self._require(run, allowed)
            yield

    def resume(self, run: Run) -> Run:
        """中断した（running のまま持ち主のいない）実行を続ける。"""
        with self._operating(run, (RUNNING,)):
            run.event("resumed", run.state.get("current"), clock=self.clock)
            self.say(f"実行 {run.id} を続けます")
            self._advance(run, self.definition(run))
        return run

    def approve(self, run: Run, message: str = "") -> Run:
        """人の答え待ちの工程を通して続ける。"""
        with self._operating(run, (WAITING,)):
            flow = self.definition(run)
            current = run.state["current"]
            entry = run.steps[current]
            entry.update(status=DONE, ended=self.clock(), out={**(entry.get("out") or {}), "approved": True,
                                                                 "message": message},
                         message=message or entry.get("message", ""))
            run.event("approved", current, message, clock=self.clock)
            run.state.update(status=RUNNING, current=flow.after(current))
            run.save(self.clock)
            self.say(f"工程 {current} を通しました")
            self._advance(run, flow)
        return run

    def reject(self, run: Run, to: str, message: str) -> Run:
        """人の答え待ちの工程から、to（その工程か前の工程）へ差し戻す（message は ${vars.feedback}）。"""
        with self._operating(run, (WAITING,)):
            flow = self.definition(run)
            current = run.state["current"]
            if to not in run.steps or flow.index(to) > flow.index(current):
                raise FlowError(ErrorCode.INVALID_INPUT, f"差し戻す先「{to}」は、工程 {current} か、その前の工程ではありません。",
                                details={"steps": [s.id for s in flow.steps[:flow.index(current) + 1]]})
            entry = run.steps[current]
            entry.update(status=FAILED, ended=self.clock(), message=message,
                         out={**(entry.get("out") or {}), "approved": False, "message": message})
            run.vars["feedback"] = message
            run.event("rejected", current, f"{to} へ：{message}", clock=self.clock)
            self._back(run, flow, to, current)
            run.state["status"] = RUNNING
            run.save(self.clock)
            self.say(f"工程 {current} から {to} へ差し戻します")
            self._advance(run, flow)
        return run

    def retry(self, run: Run) -> Run:
        """失敗した実行を、失敗した工程からやり直す。"""
        with self._operating(run, (FAILED,)):
            current = run.state["current"]
            run.steps[current].update(status=PENDING, retried=0)
            run.state["status"] = RUNNING
            run.event("retried", current, clock=self.clock)
            run.save(self.clock)
            self.say(f"工程 {current} からやり直します")
            self._advance(run, self.definition(run))
        return run

    def cancel(self, run: Run) -> Run:
        """実行を取り消す。ほかのプロセスが動かしていれば、止めてほしい印を置く（工程の区切りで止まる）。中断した工程は、
        種類の片付け（Kind.cancel。エージェントを止める 等）をしてから取り消す。"""
        if run.status in (DONE, CANCELLED):
            self._require(run, (RUNNING, WAITING, FAILED))
        try:
            with self._operating(run, (RUNNING, WAITING, FAILED)):
                self._clean_up(run)
                self._cancelled(run)
        except FlowError as error:
            if error.code != ErrorCode.RUN_LOCKED:
                raise
            (run.folder / CANCEL_FILE).write_text(str(self.clock()), encoding="utf-8")
            # 印を置く間に持ち主が止まった（待ち・失敗に移って印を消した）なら、ここで取り消す
            try:
                with lock(run):
                    run.reload()
                    if run.status in (RUNNING, WAITING, FAILED):
                        self._clean_up(run)
                        self._cancelled(run)
                    else:
                        run.forget_cancel()
                    return run
            except FlowError as again:
                if again.code != ErrorCode.RUN_LOCKED:
                    raise
            self.say(f"実行 {run.id} は動いているので、止めてほしい印を置きました（工程の区切りで止まります）")
        return run

    # ---- 中 ---------------------------------------------------------------------------------------------
    def _require(self, run: Run, allowed: tuple[str, ...]) -> None:
        status = run.shown_status if run.status == RUNNING else run.status
        if run.status in allowed:
            return
        actions = {WAITING: ["approve", "reject", "cancel"], FAILED: ["retry", "cancel"], INTERRUPTED: ["resume", "cancel"],
                   RUNNING: ["cancel"], DONE: [], CANCELLED: []}.get(status, [])
        where = f"（工程 {run.state.get('current')}）" if status in (WAITING, FAILED, INTERRUPTED) else ""
        raise FlowError(ErrorCode.INVALID_STATE, f"実行 {run.id} は{NAMES.get(status, status)}です{where}。",
                        details={"status": status, "actions": actions})

    def _clean_up(self, run: Run) -> None:
        """中断した工程（running のまま）の種類の片付け。失敗しても取り消しは続ける（ログに残す）。"""
        current = run.state.get("current")
        if current not in run.steps or run.steps[current]["status"] != RUNNING:
            return
        try:
            step = self.definition(run).step(current)
            kind = self.kinds.get(step.type)
            if kind is not None and kind.cancel is not None:
                kind.cancel(step, Context(self, run, step, True))
        except Exception as error:   # 片付けの失敗で取り消しを止めない
            run.log(current, f"取り消しの片付けに失敗しました：{getattr(error, 'message', None) or error}")

    def _cancelled(self, run: Run) -> None:
        current = run.state.get("current")
        if current in run.steps and run.steps[current]["status"] in (RUNNING, WAITING, FAILED):
            run.steps[current].update(status=CANCELLED, ended=self.clock())
        run.state["status"] = CANCELLED
        run.forget_cancel()
        run.event("cancelled", current, clock=self.clock)
        run.save(self.clock)
        self.say(f"実行 {run.id} を取り消しました")

    def _back(self, run: Run, flow: Flow, to: str, current: str) -> None:
        """to から current までを待ちに戻し、to から続ける。間の工程（to から current の手前まで）の戻り・繰り返しの
        回数は 0 に戻す（入れ子の回数は周回ごと。current の回数は残し、外側の max が全体を抑える）。"""
        for step in flow.steps[flow.index(to):flow.index(current) + 1]:
            entry = run.steps[step.id]
            entry.update(status=PENDING, retried=0)
            if step.id != current:
                entry.update(backs=0, loops=0)
                _forget(entry)
        run.state["current"] = to

    def _stop(self, run: Run, status: str) -> None:
        """待ち・終わり・失敗に移る（残った取り消しの印は消す）。"""
        run.state["status"] = status
        run.forget_cancel()

    def _advance(self, run: Run, flow: Flow) -> None:
        while True:
            current = run.state.get("current")
            if run.cancel_requested() and current is not None:
                self._cancelled(run)
                return
            if current is None:
                self._stop(run, DONE)
                run.event("finished", clock=self.clock)
                run.save(self.clock)
                self.say(f"実行 {run.id} が終わりました")
                return
            step = flow.step(current)
            entry = run.steps[current]
            resumed = entry["status"] == RUNNING
            if not resumed:
                if step.when and not _expand.evaluate(step.when, run.scope(current)):
                    _forget(entry)
                    entry.update(status=SKIPPED, ended=self.clock())
                    run.event("skipped", current, f"when（{step.when}）を満たしません", clock=self.clock)
                    run.state["current"] = flow.after(current)
                    run.save(self.clock)
                    self.say(f"工程 {current} を飛ばします（when を満たしません）")
                    continue
                _forget(entry)
                entry.update(status=RUNNING, attempts=entry.get("attempts", 0) + 1, started=self.clock(), ended=None,
                             data={})
                run.event("started", current, clock=self.clock)
                run.save(self.clock)
                count = entry["attempts"]
                self.say(f"工程 {current}（{step.type}）を始めます" + (f"（{count} 回目）" if count > 1 else ""))
            else:
                self.say(f"工程 {current}（{step.type}）を続けます（中断していました）")
            outcome = self._run_step(run, step, resumed)
            if run.cancel_requested():
                self._cancel_after(run, flow, step, outcome)
                return
            self._settle(run, flow, step, outcome)
            if run.status != RUNNING:
                return

    def _run_step(self, run: Run, step: Step, resumed: bool) -> Outcome:
        context = Context(self, run, step, resumed)
        try:
            outcome = self.kinds[step.type].run(step, context)
        except FlowError as error:
            outcome = Outcome(FAILED, error.message)
        except Exception as error:   # 種類の誤り（不具合も）は、その工程の失敗として残す（実行の記録を壊さない）
            outcome = Outcome(FAILED, getattr(error, "message", None) or str(error) or type(error).__name__)
            context.log(f"誤り（{type(error).__name__}）：{outcome.message}")
        if not isinstance(outcome, Outcome) or outcome.status not in OUTCOMES:
            outcome = Outcome(FAILED, f"工程の種類 {step.type} が、知らない結果を返しました。")
        return outcome

    def _cancel_after(self, run: Run, flow: Flow, step: Step, outcome: Outcome) -> None:
        """工程の間に取り消しの印が置かれた：終わった工程は済みとして残してから止める。"""
        entry = run.steps[step.id]
        run.vars.update(outcome.vars or {})
        entry.update(message=outcome.message or "", out=dict(outcome.out or {}), ended=self.clock())
        if outcome.status == DONE and not (step.pass_if and not _expand.evaluate(step.pass_if, run.scope(step.id))):
            entry["status"] = DONE
            run.event("done", step.id, outcome.message or "", clock=self.clock)
            run.state["current"] = flow.after(step.id)
            if run.state["current"] is None:   # 全部済んだ：取り消しではなく終わり
                self._stop(run, DONE)
                run.event("finished", clock=self.clock)
                run.save(self.clock)
                self.say(f"実行 {run.id} が終わりました")
                return
        self._cancelled(run)

    def _settle(self, run: Run, flow: Flow, step: Step, outcome: Outcome) -> None:
        current = step.id
        entry = run.steps[current]
        run.vars.update(outcome.vars or {})
        entry.update(message=outcome.message or "", out=dict(outcome.out or {}), ended=self.clock())
        status, message = outcome.status, outcome.message or ""
        if status == DONE and step.pass_if and not _expand.evaluate(step.pass_if, run.scope(current)):
            status = FAILED
            message = _expand.text_of(entry["out"].get("message")) or f"pass_if（{step.pass_if}）を満たしません"
            entry["message"] = message
        if status == WAITING:
            entry["status"] = WAITING
            entry["ended"] = None
            self._stop(run, WAITING)
            run.event("waiting", current, message, clock=self.clock)
            run.save(self.clock)
            self.say(f"工程 {current} は人の答えを待っています" + (f"：{message}" if message else ""))
            return
        if status == FAILED:
            entry["status"] = FAILED
            run.event("failed", current, message, clock=self.clock)
            self.say(f"工程 {current} が失敗しました" + (f"：{message}" if message else ""))
            if entry.get("retried", 0) < step.retries:
                entry.update(status=PENDING, retried=entry.get("retried", 0) + 1)
                run.event("retry", current, clock=self.clock)
                run.save(self.clock)
                self.say(f"工程 {current} をやり直します（{entry['retried']}/{step.retries}）")
                return
            if step.on_fail is not None and entry.get("backs", 0) < step.on_fail.max:
                entry["backs"] = entry.get("backs", 0) + 1
                feedback = _expand.expand(step.on_fail.message, run.scope(current)) if step.on_fail.message else message
                run.vars["feedback"] = feedback
                run.event("back", current, f"{step.on_fail.to} へ（{entry['backs']}/{step.on_fail.max}）", clock=self.clock)
                self._back(run, flow, step.on_fail.to, current)
                run.save(self.clock)
                self.say(f"工程 {step.on_fail.to} へ戻ります（{entry['backs']}/{step.on_fail.max}）")
                return
            self._stop(run, FAILED)
            run.save(self.clock)
            self.say(f"実行 {run.id} は工程 {current} で失敗しました")
            return
        entry["status"] = DONE
        run.event("done", current, message, clock=self.clock)
        self.say(f"工程 {current} が終わりました" + (f"：{message}" if message else ""))
        loop = step.loop
        if loop is not None and entry.get("loops", 0) < loop.max \
                and not (loop.until and _expand.evaluate(loop.until, run.scope(current))):
            entry["loops"] = entry.get("loops", 0) + 1
            run.event("loop", current, f"{loop.to} へ（{entry['loops']}/{loop.max}）", clock=self.clock)
            self._back(run, flow, loop.to, current)
            run.save(self.clock)
            self.say(f"工程 {loop.to} へ戻ります（繰り返し {entry['loops']}/{loop.max}）")
            return
        run.state["current"] = flow.after(current)
        run.save(self.clock)
