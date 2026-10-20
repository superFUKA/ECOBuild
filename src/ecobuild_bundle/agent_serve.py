"""ECOBuild の係（このPCで常駐する）：エージェントの間の取り次ぎを、画面を持つアプリから切り離して本体で行う。

- 頼み（team.REQUESTS）：コンテナの中・GUI の窓の中の進行役が書いたチームの操作（agent team …）を、このPCで実行して
  結果を書き戻す（team.forward が待っている）。
- 進行役への知らせ：作業役の返答が終わったら（Stop フックの replied.json）、進行役の受け箱に入れる（team.lead_notice）。
- 返答が終わったら、作業空間の型に手元をそろえさせる（project update。C++ では Visual Studio の構成。ほかの型は何もしない）。

エージェントを動かしているのは係ではなく、係を起動した側（GUI の窓等）。作業役を起動する・閉じる前に止める、は出来事
（emit）としてその側に頼む（止めるときは返事 ack を待つ）。起動した側がいなければ（端末から起動した）、作業役は
新しい画面で起動する（open_agent）。受け箱のものを届けるのも、エージェントを動かしている側。

ECOBuild のコマンドは run で実行する（使う側が渡す：プログラム名を本体に書かない）。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from ecobuild import settings as _settings
from ecobuild.errors import EcoBuildError, ErrorCode

from . import agent_status, team

TEAM_COMMANDS = ("start", "close", "send", "list")
LOCK = Path("agents") / "serve.lock"   # ECOBUILD_HOME の下：係はこのPCに1つ
STOP_TIMEOUT = 30                       # 作業役を止めてもらう返事を待つ秒数

Run = Callable[[list[str], Path], dict]


def failed(message: str, hint: str | None = None) -> dict:
    return {"ok": False, "result": None, "error": {"code": ErrorCode.AGENT_ERROR, "message": message, "hint": hint}}


class Serve:
    """係の1回分の見回り（step）と、その状態（返答の終わりを見た時刻）。

    run(args, cwd)：ECOBuild のコマンドを cwd で実行し、その JSON の結果（{ok, result|error}）を返す。
    emit(event)：起動した側への出来事（None なら起動した側はいない）。ack(key, timeout)：その返事を待つ（届いたか）。
    open_agent(path, role, prompt)：起動した側がいないときに、作業役を新しい画面で起動する。
    log(message)：したことを人に知らせる。"""

    def __init__(self, run: Run, *, emit: Callable[[dict], None] | None = None,
                 ack: Callable[[str, float], bool] = lambda key, timeout: True,
                 open_agent: Callable[[Path, str, str], None] | None = None,
                 log: Callable[[str], None] = lambda message: None):
        self.run, self.emit, self.ack, self.open_agent, self.log = run, emit, ack, open_agent, log
        self.started = time.time()
        self._replied: dict[Path, float] = {}

    def step(self) -> None:
        for folder in agent_status.folders():
            root = agent_status.workspace_of(folder)
            self._requests(folder, root)
            if root is not None:
                self._watch_reply(folder, root)

    # ---- 頼み -------------------------------------------------------------------------------------------
    def _requests(self, folder: Path, root: Path | None) -> None:
        inbox = folder / team.REQUESTS
        for file in sorted(inbox.glob("*.json")) if inbox.is_dir() else ():
            if file.name.endswith(".result.json"):
                continue
            taken = file.with_suffix(".taken")
            try:
                os.replace(file, taken)       # ほかが拾ったものは飛ばす
            except OSError:
                continue
            request = agent_status.read(taken)
            if not isinstance(request, dict) or not request.get("id"):
                taken.unlink(missing_ok=True)
                continue
            try:
                doc = self.handle(root, request)
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

    def handle(self, root: Path | None, request: dict) -> dict:
        """頼み1つを実行して、結果の JSON（{ok, result|error}）を返す。"""
        args = [str(a) for a in request.get("args") or []]
        if args[:2] != ["agent", "team"] or len(args) < 3 or args[2] not in TEAM_COMMANDS:
            return failed(f"この頼みは受け付けません：ecobuild {' '.join(args)}")
        if root is None:
            return failed("頼んだエージェントの作業空間が分かりません。", hint="エージェントを起動し直してください。")
        cwd = (root / str(request.get("cwd") or ".")).resolve()
        if not cwd.is_relative_to(root.resolve()):
            return failed("作業空間の外では実行しません。")
        self.log(f"頼み：ecobuild {' '.join(a for a in args if a != '--json')}（{root}）")
        if args[2] == "close" and len(args) > 3:
            try:
                member = team.find(root, args[3])
            except EcoBuildError as error:
                return {"ok": False, "result": None,
                        "error": {"code": error.code, "message": error.message, "hint": error.hint}}
            self._stop(member.path)   # 使っているフォルダーは消せない
        doc = self.run(args, cwd)
        if args[2] == "start" and doc.get("ok") and (doc.get("result") or {}).get("path"):
            doc = {**doc, "result": self._start(doc["result"], root)}
        return doc

    def _start(self, member: dict, lead: Path) -> dict:
        """作った作業役を起動する：起動した側に頼む（タブで開く）か、いなければ新しい画面で。"""
        path = Path(member["path"])
        if self.emit is not None:
            self.emit({"event": "agent-start", "path": str(path), "name": member.get("name", ""),
                       "role": member.get("role", team.WORKER), "prompt": member.get("prompt", ""), "lead": str(lead)})
            return member
        if self.open_agent is not None:
            self.open_agent(path, member.get("role", team.WORKER), member.get("prompt", ""))
            return {**member, "opened": True}
        return member

    def _stop(self, path: Path) -> None:
        """作業空間 path のエージェントを止めてもらう（起動した側がいなければ何もしない）。"""
        if self.emit is None:
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
        self.replied(root, replied.get("message") or "")

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
