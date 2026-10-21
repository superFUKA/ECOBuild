"""git の呼び出し。作業の流れ（Repository）の土台で、利用側が別のclone（依存先等）を扱うのにも使う。

git のメッセージで状況を判定する箇所があるため、メッセージは英語に固定して実行する。
"""

from __future__ import annotations

import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from ecotask import process as _process
from .errors import ErrorCode, WorkError, operation

# ECOWORK_ALLOW：ecowork 自身の呼び出しは、タスクブランチを守るフック（hooks）を通す。
_ENV = {"LANGUAGE": "en", "LC_ALL": "C.UTF-8", "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true", "ECOWORK_ALLOW": "1"}
REMOTE = "origin"
# fetch(reuse=True) は、この秒数より前に（別のコマンドが）取得したばかりなら取得し直さない（GUI が一覧・状態等を
# 続けて読むとき、コマンドごとに GitHub へ問い合わせない）。取得した時刻は .git の FETCHED_MARK に残す
RECENT_FETCH = 10
FETCHED_MARK = "ecowork-fetched"
# 同じ clone の fetch は1つずつ（GUI が読むだけのコマンドを並べて回すと、refs/remotes の更新が取り合いになり
# 「cannot lock ref」で失敗する）。.git の FETCH_LOCK を持つ間だけ fetch する。待ちきれなければロックなしで行う
FETCH_LOCK = "ecowork-fetch.lock"
FETCH_LOCK_TIMEOUT = 120
_DUBIOUS = re.compile(r"detected dubious ownership in repository at '([^']*)'")


@dataclass(frozen=True)
class WorkingTree:
    branch: str | None                 # 切り離された状態ならNone
    upstream: str | None
    ahead: int
    behind: int
    staged: tuple[str, ...] = ()
    unstaged: tuple[str, ...] = ()
    untracked: tuple[str, ...] = ()
    conflicted: tuple[str, ...] = ()
    upstream_gone: bool = False        # 追跡先が設定されているが、リモートにない（削除された）

    @property
    def clean(self) -> bool:
        return not (self.staged or self.unstaged or self.untracked or self.conflicted)


@dataclass(frozen=True)
class MergeOutcome:
    merged: bool                       # Falseなら衝突で止まっている
    conflicted: tuple[str, ...] = field(default_factory=tuple)
    already_up_to_date: bool = False


@dataclass(frozen=True)
class StashEntry:
    index: int
    message: str


# clone した作業空間の改行コードの扱い：取り出すときは記録のまま（LF）、記録するときは CRLF を LF にする。
# このPCの git が core.autocrlf=true だと CRLF で取り出され、同じ場所を改行の変換をしない git（コンテナの中等）で見ると、
# 追跡中のファイルのほぼすべてが改行だけの「変更」になる
CLONE_CONFIG = ("core.autocrlf=input",)


def clone(url: str, destination: Path, *, branch: str | None = None) -> "Git":
    """branch：取り出すブランチ（省略時は GitHub の既定のブランチ）。改行コードの扱いを CLONE_CONFIG に決めて取り出す。"""
    _run(["git", "clone", "--quiet", *(a for c in CLONE_CONFIG for a in ("--config", c)),
          *(["--branch", branch] if branch else []), url, str(destination)], cwd=None)
    return Git(destination)


class Git:
    def __init__(self, root: Path, *, command: str = ""):
        self.root = Path(root)
        self.command = command          # ヒントに書くCLIのコマンド名（errors.operation）
        self._fetched = False           # このオブジェクトで fetch したか（reuse のため）

    # 基本 ----------------------------------------------------------------

    def run(self, *args: str, check: bool = True, input: str | None = None) -> _process.Completed:
        return _run(["git", "-c", "core.quotepath=false", *args], cwd=self.root, check=check, input=input)

    def hooks_directory(self) -> Path:
        return self.root / self.output("rev-parse", "--git-path", "hooks")

    def output(self, *args: str) -> str:
        return self.run(*args).stdout.strip()

    def rev_parse(self, ref: str) -> str | None:
        completed = self.run("rev-parse", "--verify", "--quiet", ref + "^{commit}", check=False)
        return completed.stdout.strip() if completed.ok else None

    def current_branch(self) -> str | None:
        completed = self.run("symbolic-ref", "--short", "--quiet", "HEAD", check=False)
        return completed.stdout.strip() if completed.ok else None

    def working_tree(self) -> WorkingTree:
        text = self.run("status", "--porcelain=v2", "--branch", "--untracked-files=all").stdout
        branch = upstream = None
        ahead = behind = 0
        has_counts = False
        staged, unstaged, untracked, conflicted = [], [], [], []
        for line in text.splitlines():
            if line.startswith("# branch.head "):
                head = line[len("# branch.head "):]
                branch = None if head == "(detached)" else head
            elif line.startswith("# branch.upstream "):
                upstream = line[len("# branch.upstream "):]
            elif line.startswith("# branch.ab "):
                plus, minus = line[len("# branch.ab "):].split()
                ahead, behind = int(plus), -int(minus)
                has_counts = True
            elif line.startswith(("1 ", "2 ")):
                parts = line.split(" ", 8 if line[0] == "1" else 9)
                xy = parts[1]
                path = parts[-1].split("\t")[0]
                if xy[0] != ".":
                    staged.append(path)
                if xy[1] != ".":
                    unstaged.append(path)
            elif line.startswith("u "):
                conflicted.append(line.split(" ", 10)[-1])
            elif line.startswith("? "):
                untracked.append(line[2:])
        return WorkingTree(branch, upstream, ahead, behind,
                           tuple(staged), tuple(unstaged), tuple(untracked), tuple(conflicted),
                           upstream_gone=upstream is not None and not has_counts)

    # ブランチ -------------------------------------------------------------

    def fetch(self, *, reuse: bool = False) -> None:
        """GitHubの最新を取得する。reuse：読むだけの処理用。このオブジェクトで既に取得したか、RECENT_FETCH 秒以内に
        （別のコマンドが）取得したばかりなら、取得し直さない。GitHubの側を変えた後は reuse なしで取得し直す。"""
        if reuse and (self._fetched or self._fetched_recently()):
            return
        with self._fetch_lock():
            if reuse and self._fetched_recently():   # 待つ間に、別のコマンドが取得した
                self._fetched = True
                return
            self.run("fetch", "--quiet", "--prune", REMOTE)
        self._fetched = True
        try:
            self._mark().touch()
        except (OSError, WorkError):
            pass

    @contextmanager
    def _fetch_lock(self):
        """この clone の fetch を、ほかのコマンド（プロセス）と1つずつにする。ロックを持てなければ（読み取り専用の
        場所・待ちきれない等）そのまま行う（cannot lock ref はやり直しで受ける）。"""
        try:
            path = self.root / self.output("rev-parse", "--git-path", FETCH_LOCK)
            file = open(path, "a+")
        except (OSError, WorkError):
            yield
            return
        with file:
            held = _lock_file(file, FETCH_LOCK_TIMEOUT)
            try:
                yield
            finally:
                if held:
                    _unlock_file(file)

    def _mark(self) -> Path:
        return self.root / self.output("rev-parse", "--git-path", FETCHED_MARK)

    def _fetched_recently(self) -> bool:
        try:
            return abs(time.time() - self._mark().stat().st_mtime) < RECENT_FETCH   # 時計の細かさの差で少し先のこともある
        except (OSError, WorkError):
            return False

    def local_branches(self) -> list[str]:
        return self.output("for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()

    def remote_branches(self) -> list[str]:
        prefix = REMOTE + "/"
        names = self.output("for-each-ref", "--format=%(refname:short)", f"refs/remotes/{REMOTE}").splitlines()
        return [name[len(prefix):] for name in names if name.startswith(prefix) and name != prefix + "HEAD"]

    def has_local_branch(self, name: str) -> bool:
        return self.rev_parse(f"refs/heads/{name}") is not None

    def has_remote_branch(self, name: str) -> bool:
        return self.rev_parse(f"refs/remotes/{REMOTE}/{name}") is not None

    def switch(self, name: str) -> None:
        self.run("switch", "--quiet", name)

    def create_branch(self, name: str, start: str, *, switch: bool) -> None:
        if switch:
            self.run("switch", "--quiet", "--no-track", "-c", name, start)
        else:
            self.run("branch", "--no-track", name, start)

    def delete_branch(self, name: str, *, force: bool = False) -> None:
        self.run("branch", "-D" if force else "-d", name)

    def set_upstream(self, name: str) -> None:
        self.run("branch", "--quiet", f"--set-upstream-to={REMOTE}/{name}", name)

    def get_config(self, key: str) -> str | None:
        completed = self.run("config", "--local", "--get", key, check=False)
        return completed.stdout.strip() if completed.ok else None

    def set_config(self, key: str, value: str) -> None:
        self.run("config", "--local", key, value)

    def unset_config(self, key: str) -> None:
        self.run("config", "--local", "--unset", key, check=False)

    # 記録 ----------------------------------------------------------------

    def add(self, paths: tuple[str, ...] = (), *, all: bool = False) -> None:
        if all:
            self.run("add", "--all", "--", *paths)
        elif paths:
            self.run("add", "--", *paths)

    def commit(self, message: str, *, all: bool = False, amend: bool = False, allow_empty: bool = False) -> str:
        args = ["commit", "--quiet", "--message", message]
        if all:
            args.append("--all")
        if amend:
            args.append("--amend")
        if allow_empty:
            args.append("--allow-empty")
        self.run(*args)
        return self.output("rev-parse", "HEAD")

    def push(self, branch: str, *, set_upstream: bool = False, force: bool = False) -> None:
        args = ["push", "--quiet", REMOTE]
        if set_upstream:
            args.insert(2, "--set-upstream")
        if force:
            args.insert(2, "--force-with-lease")
        completed = self.run(*args, f"{branch}:{branch}", check=False)
        if completed.ok:
            return
        if "[rejected]" in completed.output or "stale info" in completed.output:
            raise WorkError(
                ErrorCode.NOT_FAST_FORWARD,
                f"GitHubの {branch} に手元にないコミットがあるため、pushできません。",
                hint=f"別の場所からpushされた変更なら {operation(self.command, 'sync')} で取り込んでから、"
                     f"手元でコミットを書き換えた（--amend等）なら {operation(self.command, 'task push --force')} で"
                     "pushしてください。",
                details=completed.output,
            )
        raise _git_error(completed)

    def push_delete(self, branch: str) -> None:
        self.run("push", "--quiet", REMOTE, "--delete", branch)

    def restore(self, paths: tuple[str, ...], *, staged: bool = False, source: str | None = None) -> None:
        """source：その版の状態にする（ステージと作業ツリーの両方。paths を省くと全体。その版にないファイルは消える）。"""
        if source is not None:
            self.run("restore", f"--source={source}", "--staged", "--worktree", "--", *(paths or (".",)))
            return
        self.run("restore", *(["--staged"] if staged else []), "--", *paths)

    def reset_hard(self, revision: str) -> None:
        self.run("reset", "--hard", revision)

    def reset_mixed(self, revision: str) -> None:
        """ブランチだけ戻す（ファイルはそのまま。捨てたコミットの変更はコミットしていない変更になる）。"""
        self.run("reset", "--mixed", "--quiet", revision)

    # 取り込み ---------------------------------------------------------------

    def merge(self, ref: str, *, message: str | None = None, ff_only: bool = False) -> MergeOutcome:
        args = ["merge", "--no-edit"]
        if ff_only:
            args.append("--ff-only")
        if message is not None:
            args += ["--message", message]
        completed = self.run(*args, ref, check=False)
        if completed.ok:
            return MergeOutcome(True, already_up_to_date="Already up to date" in completed.stdout)
        text = completed.output
        if "would be overwritten" in text:
            raise WorkError(
                ErrorCode.LOCAL_CHANGES_WOULD_BE_OVERWRITTEN,
                "取り込みで上書きされるファイルに、未コミットの変更があります。",
                hint=f"変更をコミットするか、{operation(self.command, 'stash')} で退避してから再実行してください。",
                details=text,
            )
        if ff_only and ("Not possible to fast-forward" in text or "not possible to fast-forward" in text):
            raise WorkError(
                ErrorCode.NOT_FAST_FORWARD,
                f"{ref} まで早送りできません（手元にだけあるコミットがあります）。",
                details=text,
            )
        conflicted = self.working_tree().conflicted
        if conflicted:
            return MergeOutcome(False, conflicted)
        raise _git_error(completed)

    def is_merging(self) -> bool:
        return self.rev_parse("MERGE_HEAD") is not None

    def merge_continue(self) -> str:
        if self.working_tree().conflicted:
            raise WorkError(
                ErrorCode.MERGE_CONFLICT,
                "まだ解決していない衝突があります。",
                hint=f"ファイルを直してから {operation(self.command, 'sync continue')} を実行してください。",
            )
        self.run("commit", "--quiet", "--no-edit")
        return self.output("rev-parse", "HEAD")

    def merge_abort(self) -> None:
        self.run("merge", "--abort")

    def conflict_markers(self, *revisions: str, cached: bool = False) -> tuple[str, ...]:
        """差分に残っている衝突の印（<<<<<<< 等）の場所（「パス:行」）。"""
        args = ["diff", "--check", *(["--cached"] if cached else []), *revisions]
        suffix = ": leftover conflict marker"
        text = self.run(*args, check=False).stdout
        return tuple(line[:-len(suffix)] for line in text.splitlines() if line.endswith(suffix))

    def eol_only(self, *revisions: str, cached: bool = False) -> tuple[str, ...]:
        """改行コード（CRLF と LF）だけが違うファイル。比べ方は git diff と同じ（revisions・cached）。"""
        args = ("--numstat", "--no-renames", *(["--cached"] if cached else []), *revisions, "--")
        changed = _numstat_paths(self.run("diff", *args, check=False).stdout)
        if not changed:
            return ()
        kept = set(_numstat_paths(self.run("diff", "--ignore-cr-at-eol", *args, check=False).stdout))
        return tuple(p for p in changed if p not in kept)

    def changed_files(self, base: str, head: str) -> list[tuple[str, str, int | None, int | None, bool]]:
        """base から head への変更（ファイルごとに パス・種類〔A・M・D 等〕・足した行・消した行〔バイナリは None〕・
        改行コードだけの差か）。名前の変更は、消したものと足したものに分けて数える。"""
        kinds = {}
        for line in self.output("diff", "--name-status", "--no-renames", base, head, "--").splitlines():
            kind, _, path = line.partition("\t")
            kinds[path] = kind[:1]
        eol = set(self.eol_only(base, head))
        found = []
        for line in self.output("diff", "--numstat", "--no-renames", base, head, "--").splitlines():
            added, deleted, path = line.split("\t", 2)
            found.append((path, kinds.get(path, "M"), None if added == "-" else int(added),
                          None if deleted == "-" else int(deleted), path in eol))
        return found

    def has_changes(self, base: str, head: str) -> bool:
        """headに、baseとの分岐点からのファイルの変更があるか（PRの差分と同じ見方）。"""
        return not self.run("diff", "--quiet", f"{base}...{head}", check=False).ok

    def count(self, revision_range: str) -> int:
        return int(self.output("rev-list", "--count", revision_range))

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        return self.run("merge-base", "--is-ancestor", ancestor, descendant, check=False).ok

    def is_rebasing(self) -> bool:
        for name in ("rebase-merge", "rebase-apply"):
            if (self.root / self.output("rev-parse", "--git-path", name)).exists():
                return True
        return False

    def rebase_continue(self) -> MergeOutcome:
        if self.working_tree().conflicted:
            raise WorkError(
                ErrorCode.MERGE_CONFLICT,
                "まだ解決していない衝突があります。",
                hint=f"ファイルを直してから {operation(self.command, 'sync continue')} を実行してください。",
            )
        completed = self.run("rebase", "--continue", check=False)
        if completed.ok:
            return MergeOutcome(True)
        conflicted = self.working_tree().conflicted
        if conflicted:
            return MergeOutcome(False, conflicted)
        raise _git_error(completed)

    def rebase_abort(self) -> None:
        self.run("rebase", "--abort")

    def rebase_onto(self, new_base: str, upstream: str, branch: str) -> MergeOutcome:
        completed = self.run("rebase", "--quiet", "--autostash", "--onto", new_base, upstream, branch, check=False)
        if completed.ok:
            return MergeOutcome(True)
        conflicted = self.working_tree().conflicted
        if conflicted:
            return MergeOutcome(False, conflicted)
        raise _git_error(completed)

    # 退避 -------------------------------------------------------------------

    def stash_push(self, message: str | None = None) -> bool:
        before = self.rev_parse("refs/stash")
        args = ["stash", "push", "--quiet", "--include-untracked"]
        if message:
            args += ["--message", message]
        self.run(*args)
        return self.rev_parse("refs/stash") != before

    def stash_pop(self) -> MergeOutcome:
        completed = self.run("stash", "pop", "--quiet", check=False)
        if completed.ok:
            return MergeOutcome(True)
        conflicted = self.working_tree().conflicted
        if conflicted:
            return MergeOutcome(False, conflicted)
        raise _git_error(completed)

    def stash_list(self) -> list[StashEntry]:
        lines = self.output("stash", "list", "--format=%gs").splitlines()
        return [StashEntry(index, message) for index, message in enumerate(lines)]


def _run(args: list[str], *, cwd: Path | None, check: bool = True, input: str | None = None) -> _process.Completed:
    try:
        return _process.run(args, cwd=cwd, check=check, env=_ENV, input=input)
    except _process.ProcessFailed as failure:
        raise _git_error(failure.completed) from None


def _numstat_paths(text: str) -> list[str]:
    """git diff --numstat の、中身（文字）の変わったファイル（バイナリは除く）。"""
    paths = []
    for line in text.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[0] != "-" and (parts[0], parts[1]) != ("0", "0"):
            paths.append(parts[2])
    return paths


def _lock_file(file, timeout: float) -> bool:
    """開いたファイルの排他ロックを、timeout 秒まで待って持つ（プロセスが終われば OS が外す）。持てたか。"""
    until = time.monotonic() + timeout
    while True:
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
            if time.monotonic() >= until:
                return False
            time.sleep(0.05)


def _unlock_file(file) -> None:
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


def _git_error(completed: _process.Completed) -> WorkError:
    dubious = _DUBIOUS.search(completed.output)
    if dubious:
        # 持ち主が違う場所（別のアカウント・コンテナで作った clone 等）：git が読むのを断る。生の git の文だけでは分からない
        return WorkError(
            ErrorCode.UNSAFE_REPOSITORY,
            f"git が {dubious.group(1)} を、持ち主が今のユーザーと違うため扱いません（dubious ownership）。",
            hint=f"自分の作業空間なら git config --global --add safe.directory \"{dubious.group(1)}\" で"
                 "信頼する場所に足してから、もう一度実行してください。",
            details=completed.output,
        )
    return WorkError(
        ErrorCode.GIT_ERROR,
        f"git {' '.join(completed.args[1:])} に失敗しました。",
        details=completed.output,
    )
