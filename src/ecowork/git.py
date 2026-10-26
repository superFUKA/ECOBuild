"""git の呼び出し。作業の流れ（Repository）の土台で、利用側が別のclone（依存先等）を扱うのにも使う。

git のメッセージで状況を判定する箇所があるため、メッセージは英語に固定して実行する。
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
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
# 「cannot lock ref」で失敗する）。.git の FETCH_LOCK を持つ間だけ fetch する。待ちきれなければロックなしで行う。
# FETCH_LOCK・FETCHED_MARK は共有の .git（--git-common-dir）に置く：作業空間（worktree）どうしは refs を共有する
FETCH_LOCK = "ecowork-fetch.lock"
FETCH_LOCK_TIMEOUT = 120
_CONFIG_LOCKED = re.compile(r"could not lock config file", re.IGNORECASE)
_CONFIG_LOCK_WAITS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6)   # 共有の設定の書き込みの取り合いを待つ（秒）
_DUBIOUS = re.compile(r"detected dubious ownership in repository at '([^']*)'")

# 作業空間（git worktree）を相対パスで記録する（--relative-paths）には git 2.48 以上が要る。相対パスにするのは、
# 元の clone を動かしても・コンテナの中で別の場所に見せても、作業空間がつながったままになるように
MINIMUM_VERSION = (2, 48, 0)
_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
# 作業空間のロックの理由（git worktree lock）。gc の prune で記録が消えないように、作るときに付ける
WORKTREE_LOCK_REASON = "ecobuild"


def git_version(executable: str = "git") -> tuple[int, int, int]:
    """git の版（"git version 2.45.1.windows.1" → (2, 45, 1)）。読めなければ（git がない等）ecowork の誤り。"""
    try:
        completed = _process.run([executable, "--version"], cwd=None, check=False, env=_ENV)
    except OSError:
        completed = None
    match = _VERSION.search(completed.stdout) if completed is not None and completed.ok else None
    if match is None:
        raise WorkError(ErrorCode.GIT_ERROR, "git の版を読めませんでした（git が見つからない等）。",
                        hint="ecobuild setup --install", details=None if completed is None else completed.output)
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def require_worktree_support() -> None:
    """作業空間（worktree）を作れる git（MINIMUM_VERSION 以上）でなければ止める。"""
    version = git_version()
    if version < MINIMUM_VERSION:
        raise WorkError(ErrorCode.GIT_ERROR, "git 2.48 以上が必要です（作業空間を相対パスで記録するため）。",
                        hint="ecobuild setup --install",
                        details={"version": ".".join(map(str, version)),
                                 "required": ".".join(map(str, MINIMUM_VERSION))})


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

    @property
    def branch(self) -> str | None:
        """退避したブランチ（メッセージの「WIP on <ブランチ>:」「On <ブランチ>:」から。切り離された状態なら None）。"""
        match = re.match(r"^(?:WIP on|On) ([^:]+):", self.message)
        return None if match is None or match.group(1) == "(no branch)" else match.group(1)


@dataclass(frozen=True)
class Worktree:
    """git worktree list の1つ。main：元の clone（main の作業ツリー）。"""
    path: Path
    head: str
    branch: str | None                 # 切り離された状態ならNone
    locked: bool
    prunable: bool                     # フォルダーがなくなった記録（worktree prune で片付く）
    main: bool


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
            path = self.common_directory() / FETCH_LOCK
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
        return self.common_directory() / FETCHED_MARK

    def _fetched_recently(self) -> bool:
        try:
            return abs(time.time() - self._mark().stat().st_mtime) < RECENT_FETCH   # 時計の細かさの差で少し先のこともある
        except (OSError, WorkError):
            return False

    def local_branches(self) -> list[str]:
        return self.output("for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()

    def checked_out_branches(self) -> dict[str, Path]:
        """どれかの git worktree（今いる所も含む）で取り出しているブランチ → 取り出している場所。消すと git が断る。"""
        found = self._checked_out()
        if any(not path.is_dir() for path in found.values()):
            # フォルダーを手で消した作業空間（ロック付きの記録が残り、git はまだそのパスに付けて返す）：記録を片付けて読み直す
            self.forget_missing_worktrees()
            found = self._checked_out()
        return found

    def _checked_out(self) -> dict[str, Path]:
        found = {}
        for line in self.output("for-each-ref", "--format=%(refname:short) %(worktreepath)", "refs/heads").splitlines():
            name, _, path = line.partition(" ")   # ブランチ名に空白はない
            if path:
                found[name] = Path(path) if Path(path).is_absolute() else self.root / path
        return found

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
        """この clone の設定の値：この作業空間だけの設定（--worktree）があればそれ、なければ共有の設定（--local）。
        このPC全体の設定（--global・--system）は読まない。"""
        completed = self.run("config", "--show-scope", "--get-all", key, check=False)
        values = [value for scope, _, value in (line.partition("\t") for line in completed.stdout.splitlines())
                  if scope in ("local", "worktree")]
        return values[-1].strip() if completed.ok and values else None

    def set_config(self, key: str, value: str) -> None:
        self._write_config("--local", key, value)

    def unset_config(self, key: str) -> None:
        self._write_config("--local", "--unset", key, check=False)

    def _write_config(self, *args: str, check: bool = True) -> _process.Completed:
        """設定を書く。作業空間どうしは共有の設定（.git/config）を書き合うので、ほかの作業空間が書いている最中
        （config.lock を持っている。git は待たずに断る）なら、少し待ってやり直す。"""
        for wait in (*_CONFIG_LOCK_WAITS, None):
            completed = self.run("config", *args, check=False)
            if completed.ok or wait is None or not _CONFIG_LOCKED.search(completed.stderr or ""):
                break
            time.sleep(wait)
        if check and not completed.ok:
            raise _git_error(completed)
        return completed

    def config_worktree(self, key: str, value: str | None) -> None:
        """この作業空間だけの設定（git config --worktree）。None なら外す。作業空間（linked worktree）では
        extensions.worktreeConfig を入れてから書く。作業空間を作ったことのない clone では、--local と同じ所に書く（git の仕様）。"""
        if self.is_linked_worktree():
            self.enable_worktree_config()
        if value is None:
            self._write_config("--worktree", "--unset-all", key, check=False)
        else:
            self._write_config("--worktree", key, value)

    # 作業空間（git worktree） ------------------------------------------------------

    def common_directory(self) -> Path:
        """共有の .git（作業空間どうしで共有する refs・設定・hooks の置き場所。--git-common-dir）。"""
        return Path(self.output("rev-parse", "--path-format=absolute", "--git-common-dir"))

    def common_root(self) -> Path:
        """元の clone（main の作業ツリー）。作業空間（linked worktree）の中でも、元の clone の場所を返す。"""
        return self.common_directory().parent

    def is_linked_worktree(self) -> bool:
        """作業空間（git worktree add で作ったもの）か。元の clone（main の作業ツリー）なら False。"""
        directories = self.output("rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir").splitlines()
        return not same_path(Path(directories[0]), Path(directories[-1]))

    def worktrees(self) -> list[Worktree]:
        """このリポジトリの作業ツリー（git worktree list --porcelain）。最初が元の clone。"""
        found, entry = [], {}
        for line in self.output("worktree", "list", "--porcelain").splitlines() + [""]:
            if line:
                key, _, value = line.partition(" ")
                entry[key] = value
                continue
            if "worktree" in entry:
                branch = entry.get("branch")
                found.append(Worktree(Path(entry["worktree"]), entry.get("HEAD", ""),
                                      branch.removeprefix("refs/heads/") if branch else None,
                                      "locked" in entry, "prunable" in entry, not found))
            entry = {}
        return found

    def worktree_add(self, path: Path, branch: str | None = None, *, detach_at: str | None = None) -> None:
        """作業空間（git worktree）を path に作る：branch を取り出すか、detach_at のコミットを切り離された状態で。
        いつも相対パスで記録し（--relative-paths）、gc の prune で記録が消えないようにロックする（--lock）。
        初めてのときは、共有の設定に worktree.useRelativePaths（手で git worktree add しても相対に）と
        extensions.worktreeConfig（作業空間ごとの設定。config_worktree）を書く。"""
        if (branch is None) == (detach_at is None):
            raise ValueError("branch か detach_at のどちらか1つを渡してください")
        require_worktree_support()
        self.enable_worktree_config("worktree.useRelativePaths")
        target = ["--detach", str(path), detach_at] if branch is None else [str(path), branch]
        self.run("worktree", "add", "--quiet", "--relative-paths", "--lock", "--reason", WORKTREE_LOCK_REASON, *target)

    def enable_worktree_config(self, *more: str) -> None:
        """共有の設定に extensions.worktreeConfig（作業空間ごとの設定）と more を true で書く（なければ）。"""
        for key in ("extensions.worktreeConfig", *more):
            if self.run("config", "--local", "--get", key, check=False).stdout.strip() != "true":
                self._write_config("--local", key, "true")

    @contextmanager
    def temporary_worktree(self, ref: str) -> Iterator[Path]:
        """ref を切り離された状態で取り出した、一時的な作業ツリー（共有の .git の中の ecowork/。終われば消す）。
        手元の作業ツリーに触れずにファイルを変えてコミットする操作（管理用のブランチの更新・衝突を直す取り込み）の場所。"""
        area = self.common_directory() / "ecowork"
        area.mkdir(exist_ok=True)
        place = Path(tempfile.mkdtemp(prefix="tmp-", dir=area))
        self.worktree_add(place, detach_at=ref)
        try:
            yield place
        finally:
            with suppress(WorkError):
                self.worktree_remove(place, force=True)
            with suppress(OSError):
                place.rmdir()

    def worktree_remove(self, path: Path, *, force: bool = False) -> None:
        """作業空間を消す（ロックを外してから）。消せなければ（変更がある・使用中）ロックを戻して誤りにする。"""
        self.run("worktree", "unlock", str(path), check=False)
        completed = self.run("worktree", "remove", *(["--force"] if force else []), str(path), check=False)
        if not completed.ok:
            if Path(path).exists():
                self.run("worktree", "lock", "--reason", WORKTREE_LOCK_REASON, str(path), check=False)
            raise _git_error(completed)

    def worktree_prune(self) -> None:
        """フォルダーがなくなった作業空間の記録を片付ける（ロック中の記録は git が残す）。"""
        self.run("worktree", "prune")

    def forget_missing_worktrees(self) -> list[Path]:
        """フォルダーがなくなった作業空間（元の clone 以外）の記録を、ロック中でも片付ける（作業空間はいつもロック付きで
        作るので、フォルダーを手で消すと git worktree prune では消えない）。片付けた場所を返す。

        元の clone の作業ツリーが見えないとき（コンテナ等に、共有の .git と自分の作業空間だけを付けた環境）は、ほかの
        作業空間も見えないだけなので、何もしない（sees_main_worktree）。"""
        missing = [tree.path for tree in self.worktrees() if not tree.main and not tree.path.is_dir()]
        if not missing or not self.sees_main_worktree():
            return []
        main = Git(self.common_root(), command=self.command)   # 今の場所が消えた作業空間のこともあるので、元の clone で
        for path in missing:
            main.run("worktree", "unlock", str(path), check=False)
        main.run("worktree", "prune", check=False)
        return missing

    def sees_main_worktree(self) -> bool:
        """元の clone の作業ツリーが、今の環境から見えるか：元の clone で取り出している一番上の項目（HEAD）のどれかがある。
        今の場所を含むもの（付けた作業空間の上のフォルダーは、中身がなくても作られる）は数えない。見えなければ、この環境は
        リポジトリの一部（共有の .git と自分の作業空間）だけを付けたもの。調べられない（HEAD がない等）ときも、見えないとする
        （分からなければ、ほかの作業空間の記録に触らない）。"""
        main = self.common_root()
        if not main.is_dir():
            return False
        listed = Git(main, command=self.command).run("ls-tree", "--name-only", "-z", "HEAD", check=False)
        if not listed.ok:
            return False
        here = Path(self.root).resolve()
        for name in listed.stdout.split("\0"):
            place = main / name
            if name and (place.exists() or place.is_symlink()) and not here.is_relative_to(place.resolve()):
                return True
        return False

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

    def changed_files(self, *revisions: str, cached: bool = False,
                      paths: tuple[str, ...] = ()) -> list[tuple[str, str, int | None, int | None, bool]]:
        """revisions（base, head 等。比べ方は git diff と同じ：なしは未ステージの変更、cached はステージ済み）の変更
        （ファイルごとに パス・種類〔A・M・D 等〕・足した行・消した行〔バイナリは None〕・改行コードだけの差か）。
        名前の変更は、消したものと足したものに分けて数える。paths：このファイル・ディレクトリだけ。"""
        args = ("--no-renames", *(["--cached"] if cached else []), *revisions, "--", *paths)
        kinds = {}
        for line in self.output("diff", "--name-status", *args).splitlines():
            kind, _, path = line.partition("\t")
            kinds[path] = kind[:1]
        eol = set(self.eol_only(*revisions, cached=cached)) if kinds else set()
        found = []
        for line in self.output("diff", "--numstat", *args).splitlines():
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

    def is_reverting(self) -> bool:
        return self.rev_parse("REVERT_HEAD") is not None

    def revert_continue(self) -> MergeOutcome:
        """止まっている取り消し（revert）を続ける（残りのコミットの取り消しも）。衝突は登録してから呼ぶ。
        直した結果が今と同じ（そのコミットの取り消しが空）なら、そのコミットは飛ばして続ける。"""
        empty = self.run("diff", "--cached", "--quiet", "HEAD", check=False).ok
        completed = self.run("revert", "--skip" if empty else "--continue", check=False)
        if completed.ok:
            return MergeOutcome(True)
        conflicted = self.working_tree().conflicted
        if conflicted:
            return MergeOutcome(False, conflicted)
        raise _git_error(completed)

    def revert_abort(self) -> None:
        self.run("revert", "--abort")

    def stopped(self) -> str | None:
        """衝突等で止まっている操作：rebase（載せ替え）・merge（取り込み）・revert（取り消し）・stash（退避した変更を
        戻すときの衝突：ほかに止まっている操作のない衝突）。なければ None。"""
        if self.is_rebasing():
            return "rebase"
        if self.is_merging():
            return "merge"
        if self.is_reverting():
            return "revert"
        return "stash" if self.working_tree().conflicted else None

    def take_side(self, paths: tuple[str, ...], *, incoming: bool) -> None:
        """衝突したファイルを片方の側の内容にして登録する：今の側（HEAD。git の --ours）か、入ってくる側（取り込む
        ブランチ・載せ替えるコミット・取り消し・戻す退避。--theirs）。その側で消えているファイルは消す。"""
        stage = "3" if incoming else "2"
        for path in paths:
            if not self.run("rev-parse", "--verify", "--quiet", f":{stage}:{path}", check=False).ok:
                self.run("rm", "--quiet", "--", path)
            else:
                self.run("checkout", "--theirs" if incoming else "--ours", "--", path)
                self.run("add", "--", path)

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

    def stash_pop(self, index: int | None = None) -> MergeOutcome:
        """退避した変更を戻す。index：stash@{index}（省略すると最後に退避したもの）。"""
        completed = self.run("stash", "pop", "--quiet", *([f"stash@{{{index}}}"] if index is not None else []),
                             check=False)
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
    if cwd is not None and not Path(cwd).is_dir():
        # 消えた場所（フォルダーを手で消した作業空間等）：OS の誤りで落ちず、場所を添えた git の誤りにする
        raise WorkError(ErrorCode.GIT_ERROR, f"{cwd} がありません（git {' '.join(args[1:4])} を実行できません）。",
                        hint="フォルダーを消した作業空間なら、もう一度実行すると記録を片付けます。")
    try:
        return _process.run(args, cwd=cwd, check=check, env=_ENV, input=input)
    except _process.ProcessFailed as failure:
        raise _git_error(failure.completed) from None


def same_path(a: Path, b: Path) -> bool:
    """同じ場所か（大文字と小文字・区切りの違いを除いて）。"""
    try:
        a, b = Path(a).resolve(), Path(b).resolve()
    except OSError:
        pass
    return os.path.normcase(a) == os.path.normcase(b)


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
