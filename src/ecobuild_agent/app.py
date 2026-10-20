"""アプリ用の起動のエージェント（Claude Code の claude -p を stream-json で動かす。係が持つ）。

AI（進行役の頼み）が起動したエージェントは、端末の画面ではなく、係（serve）がプロセスとして持つ（人が起動したものは
今までどおり対話型）：
- 起動：コンテナの中で claude -p --input-format stream-json --output-format stream-json …（起動のしかた Launch は
  AgentModule.app_launch が作る。会話の ID・役・モデル・使い方の文・設定は対話型と同じ作り方）。標準出力は状態の置き場所の
  events.jsonl に直接追記させる（係が止まっても、エージェントは返答を終えるまで書ける。次の係が続きを読む）。
- 係は見回りのたびに events.jsonl の新しい行を読み、様子（state.json）を書き、返答の終わり（result）で replied.json を
  書く（係の _watch_reply が進行役に知らせる。返答の途中で終わったときも書く）。受け箱のもの（言付け・知らせ）は、作業中でも
  すぐ標準入力へ入れる（Claude Code は返答を止めずに次の区切りで読む）。
- 止める：標準入力を閉じる（返答を終えてから終わる）。待ちきれなければ、中のプロセスごと止める。
- 持っているものは ECOBUILD_HOME/agents/app.json に覚える（係が終わっても消さない）。係が終わるときは標準入力を閉じて
  少し待つだけで、返答の途中のものは返答を終えるまで動く。次の係はそれを引き継いで出来事を読み、終わっていれば
  --resume で起こす（adopt・wake）。
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ecobuild import settings as _settings
from ecobuild.errors import EcoBuildError

from . import status
from .errors import ErrorCode

EVENTS = "events.jsonl"     # 置き場所の中：Claude Code の出来事（1行1つ。起動し直しても追記）と、係の印（type ecobuild）
ERRORS = "app-stderr.log"   # 置き場所の中：Claude Code の標準エラー
HELD = Path("agents") / "app.json"   # ECOBUILD_HOME の下：係が持っているもの（作業空間・会話の ID・役）
FLAGS = ("-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--replay-user-messages")
STOP_WAIT = 60      # 止める（閉じる・起動し直す・引き取る）とき、返答を終えるのを待つ秒数（過ぎれば止める）
CLOSE_WAIT = 8      # 係が終わるとき、返答を終えるのを待つ秒数（過ぎても止めない：返答を終えて自分で終わる）
INTERRUPTED_PROMPT = ("ECOBuild の係が起動し直したので、前の会話の続きから起こしました。返答の途中で止まっていたら、"
                      "止まっていたところから続けてください。")
HANDBACK_PROMPT = ("人との会話（引き取り）が終わり、ECOBuild の係に戻りました。人と決めたことに沿って、任された仕事を"
                   "続けてください（終わっていれば、報告・提出まで）。")
TOOL_KEYS = ("command", "file_path", "notebook_path", "pattern", "url", "query", "description", "skill", "prompt")


@dataclass(frozen=True)
class Launch:
    """アプリ用の起動のしかた（AgentModule.app_launch が作る）。kill：中のプロセスを止める（待ちきれないとき）。"""
    root: Path
    folder: Path
    argv: tuple[str, ...]
    env: dict | None
    session: str
    role: str
    kill: Callable[[], None] | None = field(default=None, compare=False)


def message_line(text: str) -> bytes:
    """標準入力に入れる1行（stream-json の user の発言）。"""
    return (json.dumps({"type": "user", "message": {"role": "user", "content": text}}, ensure_ascii=False)
            + "\n").encode("utf-8")


def tool_summary(name: str, given) -> str:
    """道具を使った1行（今していること）：「Bash：ecobuild test」「Edit：src/x.py」。"""
    given = given if isinstance(given, dict) else {}
    detail = next((given[key] for key in TOOL_KEYS if isinstance(given.get(key), str) and given[key].strip()), "")
    detail = " ".join(detail.split())
    if detail.startswith("/work/"):
        detail = detail[len("/work/"):]
    detail = detail if len(detail) <= 120 else detail[:119] + "…"
    return f"{name}：{detail}" if detail else name


def read_events(folder: Path, *, after: int | None = None, tail: int = 50) -> tuple[list[dict], int]:
    """events.jsonl の出来事と、次に読む位置（after に渡す。ファイルの中の位置）。after：その位置より後のすべて。
    なければ最後の tail 個（0 ならすべて）。書きかけの行は読まない。"""
    try:
        with open(Path(folder) / EVENTS, "rb") as file:
            file.seek(max(0, after or 0))
            data = file.read()
    except OSError:
        return [], max(0, after or 0)
    complete = data[:data.rfind(b"\n") + 1]
    events = []
    for line in complete.splitlines():
        try:
            event = json.loads(line.decode("utf-8", "replace"))
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    if after is None and tail:
        events = events[-tail:]
    return events, max(0, after or 0) + len(complete)


def recent_events(folder: Path, size: int = 65536) -> list[dict]:
    """events.jsonl の終わりの出来事（終わりの size バイトの中の、全部そろった行。一覧に最新の数行を出すため：
    長く伸びたファイルも全部は読まない）。"""
    try:
        with open(Path(folder) / EVENTS, "rb") as file:
            file.seek(0, os.SEEK_END)
            end = file.tell()
            file.seek(max(0, end - size))
            data = file.read()
    except OSError:
        return []
    if end > size:
        data = data[data.find(b"\n") + 1:]   # 途中から読んだ最初の行は欠けている
    events = []
    for line in data[:data.rfind(b"\n") + 1].splitlines():
        try:
            event = json.loads(line.decode("utf-8", "replace"))
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def record(folder: Path, event: str, **values) -> None:
    """events.jsonl に係の印を1行足す（Claude Code が書いていない間だけ：起動の前・終わった後）。"""
    line = json.dumps({"type": "ecobuild", "event": event, "at": time.time(), **values}, ensure_ascii=False) + "\n"
    with open(Path(folder) / EVENTS, "ab") as file:
        file.write(line.encode("utf-8"))


class Agent:
    """係が持つアプリ用のエージェント1つ。process（このPCの子プロセス）か、前の係から引き継いだもの（pid だけ）。"""

    def __init__(self, root: Path, folder: Path, *, session: str = "", role: str = "", launch: Launch | None = None,
                 process: subprocess.Popen | None = None, pid: int | None = None, stopping: bool = False,
                 log: Callable[[str], None] = lambda message: None):
        self.root, self.folder, self.session, self.role = Path(root), Path(folder), session, role
        self.launch, self.process, self.log = launch, process, log
        self.pid = process.pid if process is not None else pid
        self.stopping = stopping   # 止めた（終わっても進行役に知らせない）
        self.ended = False
        self.waking = False        # 引き継いだものを起こす（係が一度だけ）
        self._lock = threading.Lock()
        found = status.read(self.folder / status.STATE)
        self.state = found if isinstance(found, dict) else {}

    # ---- 起動 ---------------------------------------------------------------------------------------------
    @classmethod
    def start(cls, launch: Launch, log: Callable[[str], None] = lambda message: None) -> Agent:
        folder = Path(launch.folder)
        folder.mkdir(parents=True, exist_ok=True)
        before = status.read(folder / status.STATE)
        before = before if isinstance(before, dict) else {}
        record(folder, "start", session=launch.session, role=launch.role)
        out, err = open(folder / EVENTS, "ab"), open(folder / ERRORS, "ab")
        try:
            process = subprocess.Popen(list(launch.argv), stdin=subprocess.PIPE, stdout=out, stderr=err, env=launch.env,
                                       cwd=str(launch.root), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                       start_new_session=os.name != "nt")
        except OSError as error:
            raise EcoBuildError(ErrorCode.AGENT_ERROR, f"エージェントを起動できませんでした：{error}") from error
        finally:
            out.close()
            err.close()
        agent = cls(launch.root, folder, session=launch.session, role=launch.role, launch=launch, process=process, log=log)
        agent.state = {"mode": status.APP, "state": status.IDLE, "since": time.time(), "session": launch.session,
                       "role": launch.role, "pid": process.pid, "read": (folder / EVENTS).stat().st_size,
                       "at": time.time(), **{k: before[k] for k in ("last_reply", "replied_at", "limits") if k in before}}
        agent._save()
        status.started(folder, process.pid, status.APP)
        return agent

    @property
    def stdin_open(self) -> bool:
        return self.process is not None and self.process.stdin is not None and not self.process.stdin.closed

    # ---- 入力 ---------------------------------------------------------------------------------------------
    def send(self, text: str) -> bool:
        """発言を標準入力に入れる（作業中でもすぐ）。入れられなければ False。"""
        if not self.stdin_open or self.ended:
            return False
        try:
            self.process.stdin.write(message_line(text))
            self.process.stdin.flush()
        except (OSError, ValueError):
            return False
        with self._lock:
            if self.state.get("state") != status.WORKING:
                self.state.update(state=status.WORKING, since=time.time(), doing="", doing_at=None)
            self._save()
        return True

    def close_input(self) -> None:
        """標準入力を閉じる（Claude Code は返答を終えてから終わる）。"""
        if self.stdin_open:
            try:
                self.process.stdin.close()
            except OSError:
                pass

    # ---- 見回り -------------------------------------------------------------------------------------------
    def alive(self) -> bool:
        if self.process is not None:
            return self.process.poll() is None
        return self.pid is not None and status.alive(self.pid)

    def poll(self) -> None:
        """新しい出来事を読み、終わっていれば片付ける。"""
        with self._lock:
            if self.ended:
                return
            self._read()
            if not self.alive():
                self._read()
                self._end()

    def _read(self) -> None:
        file = self.folder / EVENTS
        start = self.state.get("read") if isinstance(self.state.get("read"), int) else 0
        try:
            with open(file, "rb") as found:
                found.seek(start)
                data = found.read()
        except OSError:
            return
        complete = data[:data.rfind(b"\n") + 1]
        if not complete:
            return
        for line in complete.splitlines():
            try:
                event = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            if isinstance(event, dict):
                self._event(event)
        self.state["read"] = start + len(complete)
        self._save()

    def _event(self, event: dict) -> None:
        kind, now = event.get("type"), time.time()
        if kind == "system" and event.get("subtype") == "init":
            self.session = str(event.get("session_id") or self.session)
            self.state.update(session=self.session, model=event.get("model"))
        elif kind == "system" and event.get("subtype") == "api_retry":
            self.state.update(doing="（API の一時的な失敗。やり直しを待っています）", doing_at=now)
        elif kind == "assistant":
            message = event.get("message") if isinstance(event.get("message"), dict) else {}
            for block in message.get("content") or ():
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    self.state.update(doing=tool_summary(str(block.get("name") or "道具"), block.get("input")), doing_at=now)
                elif block.get("type") == "text" and str(block.get("text") or "").strip():
                    self.state["last_text"] = str(block["text"])[-2000:]
            usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
            used = sum(usage.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            if used:
                self.state["context_tokens"] = used
            if self.state.get("state") != status.WORKING:
                self.state.update(state=status.WORKING, since=now)
        elif kind == "user" and isinstance((event.get("message") or {}).get("content"), str):
            if self.state.get("state") != status.WORKING:   # 入れた発言を読んだ（replay）
                self.state.update(state=status.WORKING, since=now, doing="", doing_at=None)
        elif kind == "rate_limit_event":
            windows = (event.get("rate_limit_info") or {}).get("unifiedWindows") or {}
            limits = dict(self.state.get("limits") or {})
            for name, window in windows.items():
                if isinstance(window, dict) and isinstance(window.get("utilization"), (int, float)):
                    limits[name] = {"used_percentage": round(window["utilization"] * 100, 1),
                                    "resets_at": window.get("resetsAt"), "at": now}
            self.state["limits"] = limits
        elif kind == "result":
            self._result(event, now)

    def _result(self, event: dict, now: float) -> None:
        text = event.get("result") if isinstance(event.get("result"), str) else self.state.get("last_text") or ""
        error = ""
        if event.get("is_error"):
            error = str(event.get("subtype") or "error") + (f"（{event['api_error_status']}）"
                                                             if event.get("api_error_status") else "")
        usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
        models = event.get("modelUsage") if isinstance(event.get("modelUsage"), dict) else {}
        window = next((m.get("contextWindow") for m in models.values() if isinstance(m, dict) and m.get("contextWindow")), 0)
        denials = event.get("permission_denials") if isinstance(event.get("permission_denials"), list) else []
        self.state.update(
            state=status.WORKING if event.get("queued_turn_count") else status.IDLE, since=now, replied_at=now,
            last_reply=text[:2000], doing="", doing_at=None, error=error, denials=denials,
            usage={"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
                   "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
                   "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
                   "cost_usd": event.get("total_cost_usd"), "duration_ms": event.get("duration_ms"),
                   "num_turns": event.get("num_turns")})
        if window and self.state.get("context_tokens"):
            self.state["context"] = round(self.state["context_tokens"] * 100 / window, 1)
        message = text
        if error:
            message += f"\n（エラーで返答を終えました：{error}）"
        if denials:
            message += f"\n（断られた権限が {len(denials)} 件あります）"
        status._write(self.folder / "replied.json", {"at": now, "message": message})

    def _end(self) -> None:
        """プロセスが終わった。止めたのでなければ、進行役に知らせる（返答の終わりとして）。"""
        self.ended = True
        code = self.process.returncode if self.process is not None else None
        was = self.state.get("state")
        self.state.update(state=status.STOPPED, since=time.time(), doing="", doing_at=None, ended_working=was == status.WORKING)
        record(self.folder, "exit", code=code, requested=self.stopping)
        if not self.stopping:
            detail = _tail(self.folder / ERRORS)
            message = (f"（エージェント〔Claude Code〕が{'返答の途中で' if was == status.WORKING else ''}終わりました"
                       f"{f'：終了コード {code}' if code is not None else ''}。"
                       "agent team restart で起動し直せます）" + (f"\n{detail}" if detail else ""))
            self.state["error"] = message
            status._write(self.folder / "replied.json", {"at": time.time(), "message": message})
        self._save()   # running.json は残す（mode app のまま、プロセスが終わっているので「止まっている」）

    def _save(self) -> None:
        self.state["at"] = time.time()
        try:
            status._write(self.folder / status.STATE, self.state)
        except OSError:
            pass

    # ---- 止める -------------------------------------------------------------------------------------------
    def stop(self, wait: float = STOP_WAIT) -> bool:
        """返答を終えさせてから止める（標準入力を閉じて wait 秒待つ。過ぎれば中のプロセスごと止める）。返答を終えて
        止まったか。"""
        self.stopping = True
        self.close_input()
        until = time.monotonic() + wait
        while time.monotonic() < until:
            self.poll()
            if self.ended:
                return True
            time.sleep(0.2)
        self.log(f"エージェントが {int(wait)} 秒で返答を終えなかったので止めます（{self.root}）")
        if self.launch is not None and self.launch.kill is not None:
            try:
                self.launch.kill()
            except Exception:   # 中を止められなくても、こちらは止める
                pass
        if self.pid is not None:
            status.stop(self.pid)
        if self.process is not None:
            try:
                self.process.wait(10)
            except subprocess.TimeoutExpired:
                pass
        self.poll()
        return False


def _tail(file: Path, size: int = 600) -> str:
    try:
        data = file.read_bytes()[-size:]
    except OSError:
        return ""
    return data.decode("utf-8", "replace").strip()


class Apps:
    """係が持つアプリ用のエージェント（作業空間ごとに1つ）。

    launch(root, role, resume, progress) → Launch：起動のしかた（使う側が渡す：AgentModule を本体の係は知らない）。"""

    def __init__(self, launch: Callable[..., Launch], log: Callable[[str], None] = lambda message: None):
        self.launch, self.log = launch, log
        self._agents: dict[str, Agent] = {}
        self._lock = threading.Lock()
        self._held = threading.Lock()   # HELD を書く（作業役の作成は並べて行うので、起動も重なる）

    @staticmethod
    def _key(root: Path) -> str:
        return os.path.normcase(str(Path(root).resolve()))

    def get(self, root: Path) -> Agent | None:
        with self._lock:
            return self._agents.get(self._key(root))

    def holds(self, root: Path) -> bool:
        found = self.get(root)
        return found is not None and not found.ended

    def agents(self) -> list[Agent]:
        with self._lock:
            return list(self._agents.values())

    def start(self, root: Path, *, role: str = "", prompt: str = "", resume: str = "",
              progress: Callable[[str], None] = lambda message: None) -> Agent:
        """作業空間 root のエージェントをアプリ用で起動し（resume：その会話の続きから）、prompt があれば最初に入れる。"""
        if self.holds(root):
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "この作業空間のエージェントは、もう係が動かしています。",
                                hint="agent team list で様子を見られます。")
        launch = self.launch(root, role, resume, progress)
        if status.running_mode(launch.folder) == "":
            raise EcoBuildError(ErrorCode.AGENT_ERROR, "この作業空間のエージェントは、対話型（人の画面）で動いています。",
                                hint="その画面を閉じてから（引き取ったものなら agent team handback で）やり直してください。")
        agent = Agent.start(launch, self.log)
        with self._lock:
            self._agents[self._key(root)] = agent
        self._remember()
        if prompt.strip():
            agent.send(prompt)
        self.log(f"エージェントをアプリ用で起動しました（{root}{'・続きから' if resume else ''}）")
        return agent

    def stop(self, root: Path, wait: float = STOP_WAIT) -> Agent | None:
        """作業空間 root のエージェントを止めて、持つのをやめる（返答を終えさせてから）。"""
        with self._lock:
            agent = self._agents.pop(self._key(root), None)
        self._remember()
        if agent is not None and not agent.ended:
            agent.stop(wait)
        return agent

    def step(self) -> list[Agent]:
        """見回り：出来事を読み、受け箱のものを標準入力へ入れる。返すもの：前の係から引き継ぎ、終わったので起こすもの。"""
        wake = []
        for agent in self.agents():
            agent.poll()
            if agent.ended:
                if agent.process is None and not agent.waking:
                    agent.waking = True
                    wake.append(agent)
                continue
            while agent.stdin_open and (item := status.take(agent.folder)) is not None:
                if not agent.send(str(item.get("text") or "")):
                    status.put(agent.folder, str(item.get("text") or ""), sender=str(item.get("from") or ""))
                    break
        return wake

    def close(self, wait: float = CLOSE_WAIT) -> None:
        """係が終わるとき：標準入力を閉じ（返答を終えて終わる）、wait 秒まで出来事を読む。止めない・覚えたまま
        （次の係が引き継ぎ、続きから起こす）。"""
        agents = [agent for agent in self.agents() if not agent.ended]
        for agent in agents:
            agent.stopping = True
            agent.close_input()
        until = time.monotonic() + wait
        while agents and time.monotonic() < until:
            for agent in agents:
                agent.poll()
            agents = [agent for agent in agents if not agent.ended]
            time.sleep(0.2)
        self._remember()

    def adopt(self) -> list[Agent]:
        """前の係が持っていたもの（HELD）を引き継ぐ（出来事を読み続け、終わったら step が起こすものとして返す）。"""
        found = status.read(_settings.home() / HELD)
        adopted = []
        for entry in found.get("agents") or () if isinstance(found, dict) else ():
            root, folder = Path(str(entry.get("root") or "")), Path(str(entry.get("folder") or ""))
            if not entry.get("root") or not root.is_dir() or not folder.is_dir() or self.get(root) is not None:
                continue
            running = status.read(folder / status.RUNNING)
            pid = running.get("pid") if isinstance(running, dict) and running.get("mode") == status.APP else None
            agent = Agent(root, folder, session=str(entry.get("session") or ""), role=str(entry.get("role") or ""),
                          pid=pid if isinstance(pid, int) else None, stopping=True, log=self.log)
            with self._lock:
                self._agents[self._key(root)] = agent
            adopted.append(agent)
        return adopted

    def _remember(self) -> None:
        """持っているものを HELD に書く（係が終わっても残す）。"""
        held = [{"root": str(agent.root), "folder": str(agent.folder), "session": agent.session, "role": agent.role}
                for agent in self.agents()]
        path = _settings.home() / HELD
        with self._held:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                status._write(path, {"agents": held})
            except OSError:
                pass
