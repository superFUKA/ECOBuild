"""git の呼び出し。作業の流れ（Repository）の土台で、利用側が別のclone（依存先等）を扱うのにも使う。

git のメッセージで状況を判定する箇所があるため、メッセージは英語に固定して実行する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import _process
from .errors import ErrorCode, WorkError, operation

_ENV = {"LANGUAGE": "en", "LC_ALL": "C.UTF-8", "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true"}
REMOTE = "origin"


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


def clone(url: str, destination: Path) -> "Git":
    _run(["git", "clone", "--quiet", url, str(destination)], cwd=None)
    return Git(destination)


class Git:
    def __init__(self, root: Path, *, command: str = ""):
        self.root = Path(root)
        self.command = command          # ヒントに書くCLIのコマンド名（errors.operation）

    # 基本 ----------------------------------------------------------------

    def run(self, *args: str, check: bool = True) -> _process.Completed:
        return _run(["git", "-c", "core.quotepath=false", *args], cwd=self.root, check=check)

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
                           tuple(staged), tuple(unstaged), tuple(untracked), tuple(conflicted))

    # ブランチ -------------------------------------------------------------

    def fetch(self) -> None:
        self.run("fetch", "--quiet", "--prune", REMOTE)

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
                     f"手元でコミットを書き換えた（--amend等）なら {operation(self.command, 'push --force')} で"
                     "pushしてください。",
                details=completed.output,
            )
        raise _git_error(completed)

    def push_delete(self, branch: str) -> None:
        self.run("push", "--quiet", REMOTE, "--delete", branch)

    def restore(self, paths: tuple[str, ...], *, staged: bool = False) -> None:
        self.run("restore", *(["--staged"] if staged else []), "--", *paths)

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
                hint=f"ファイルを直してから {operation(self.command, 'add')} で登録してください。",
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
                hint=f"ファイルを直してから {operation(self.command, 'add')} で登録してください。",
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


def _run(args: list[str], *, cwd: Path | None, check: bool = True) -> _process.Completed:
    try:
        return _process.run(args, cwd=cwd, check=check, env=_ENV)
    except _process.ProcessFailed as failure:
        raise _git_error(failure.completed) from None


def _git_error(completed: _process.Completed) -> WorkError:
    return WorkError(
        ErrorCode.GIT_ERROR,
        f"git {' '.join(completed.args[1:])} に失敗しました。",
        details=completed.output,
    )
