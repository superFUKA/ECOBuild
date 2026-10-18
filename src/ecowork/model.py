"""タスク（GitHub Issue）、タスクブランチ、ブランチ、PRと、操作の結果。"""

from __future__ import annotations

import datetime as _datetime
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ecotask import model as _model
from ecotask.tracker import TaskRef  # 親子・依存の相手（ecowork の公開APIとして、ここからも使う）

from . import github as _github
from .errors import ErrorCode, WorkError

if TYPE_CHECKING:
    from .repository import Repository

TASK_BRANCH_PREFIX = "task/"
_TASK_BRANCH = re.compile(r"task/(\d+)(?:-.+)?")


def task_branch_name(number: int, name: str | None = None) -> str:
    """タスクブランチの名前：task/<番号>-<名前>（名前がなければ task/<番号>。名前を付ける前に作ったものはこの形）。"""
    return f"{TASK_BRANCH_PREFIX}{number}" + (f"-{name}" if name else "")


# タスクブランチの名前に使えない文字：gitの決まりと、Windowsのファイル名に使えない文字、Issueの印（HTMLのコメント）を
# 壊す文字。日本語はそのまま使える。
_UNUSABLE = re.compile(r'[\s~^:?*\[\]\\/"<>|\x00-\x1f\x7f]+|\.{2,}|@\{')


def branch_label(title: str) -> str:
    """題名から作る、タスクブランチの名前の既定（使えない文字を - にする。何も残らなければ空）。"""
    label = re.sub(r"-{2,}", "-", _UNUSABLE.sub("-", title)).strip("-.")
    while label.endswith(".lock"):
        label = label.removesuffix(".lock").rstrip("-.")
    return label


def check_branch_label(name: str) -> str:
    """タスクブランチの名前（task/<番号>- の後ろ）を確かめて返す。空か、使えない文字があれば止める。"""
    name = name.strip()
    if not name:
        raise WorkError(ErrorCode.BRANCH_NAME_REQUIRED, "タスクブランチの名前を指定してください。",
                        hint="--name で指定します（日本語も使えます。例：--name ログイン画面）。")
    if branch_label(name) != name:
        raise WorkError(ErrorCode.INVALID_BRANCH_NAME, f"タスクブランチの名前に使えない文字があります：{name}",
                        hint=f'空白と ~ ^ : ? * [ ] \\ / " < > | と「..」は使えません（例：{branch_label(name) or "ログイン画面"}）。')
    return name


def is_task_branch(name: str) -> bool:
    return name.startswith(TASK_BRANCH_PREFIX)


def task_number(name: str) -> int | None:
    match = _TASK_BRANCH.fullmatch(name)
    return None if match is None else int(match.group(1))


def base_key(branch: str) -> str:
    """タスクブランチの作成元を記録するgitの設定のキー（手元の写し。本体はIssueの本文の印）。"""
    return f"branch.{branch}.ecowork-base"


# タスクブランチの本体はGitHubにあり、手元はその写し（消しても task start で作り直せる）。
# 作成元とタスクブランチの名前もGitHubに残すため、Issueの本文の末尾に印（表示されないHTMLのコメント）を書く。
_BASE_MARK = re.compile(r"\s*<!-- ecowork-base: (\S+)(?: branch: (\S+))? -->\s*$")


def issue_base(body: str) -> str | None:
    match = _BASE_MARK.search(body or "")
    return None if match is None else match.group(1)


def issue_branch(body: str) -> str | None:
    """Issueに記録したタスクブランチの名前（名前を記録する前に作ったものはNone）。"""
    match = _BASE_MARK.search(body or "")
    return None if match is None else match.group(2)


def without_base(body: str) -> str:
    return _BASE_MARK.sub("", body or "")


def with_base(body: str, base: str, branch: str | None = None) -> str:
    """作成元（とタスクブランチの名前）の印を書いた本文。branch を省くと、記録してある名前を残す。"""
    branch = branch or issue_branch(body)
    text = without_base(body)
    return (text + "\n\n" if text else "") + f"<!-- ecowork-base: {base}" + (f" branch: {branch}" if branch else "") + " -->"


# タスクブランチのPRとIssueのつながり：本文の行 Closes #<番号>（マージでIssueを閉じる）か Refs #<番号>（途中の反映）。
# 本文の作成・書き換え・途中の反映かの判定は、すべてこの関数で行う。
_LINK = re.compile(r"(?im)^(closes|refs) #(\d+)\s*$")


def task_link(body: str, task: int) -> str | None:
    """本文にある、そのIssueとのつながり（"closes"／"refs"）。複数あれば最初のもの。"""
    for match in _LINK.finditer(body or ""):
        if int(match.group(2)) == task:
            return match.group(1).lower()
    return None


def link_line(task: int, *, partial: bool) -> str:
    return f"{'Refs' if partial else 'Closes'} #{task}"


def with_task_link(body: str, task: int, *, partial: bool) -> str:
    """そのIssueとのつながりの行がなければ、先頭に足す（あれば本文のまま）。"""
    if task_link(body, task) is not None:
        return body
    return link_line(task, partial=partial) + ("\n\n" + body if body else "\n")


def with_link_kind(body: str, task: int, *, partial: bool) -> str:
    """つながりの行を、中間提出（Refs）か最後の提出（Closes）に合わせる（なければ先頭に足す）。"""
    for match in _LINK.finditer(body or ""):
        if int(match.group(2)) == task:
            return body[:match.start()] + link_line(task, partial=partial) + body[match.end():]
    return with_task_link(body, task, partial=partial)


@dataclass(frozen=True)
class Task:
    """GitHub Issue。"""

    number: int
    title: str
    url: str
    state: str
    _repository: "Repository" = field(repr=False, compare=False)
    labels: tuple[str, ...] = ()
    assignees: tuple[str, ...] = ()  # 担当者（ログイン名）
    milestone: str | None = None

    @classmethod
    def _from(cls, repository: "Repository", info: _github.IssueInfo) -> "Task":
        return cls(info.number, info.title, info.url, info.state, repository, info.labels, info.assignees,
                   info.milestone)

    def start(self, *, base: str | None = None, name: str | None = None, ignore_blocked: bool = False,
              take_over: bool = False) -> "TaskBranch":
        """タスクブランチを作る。name：新しく作るときの名前（task/<番号>-<名前>。既にあれば使わない）。None なら
        task/<番号>。空なら、新しく作るときに止める（名前を必ず入れてもらう利用側向け）。
        新しく作るときは、先に終わるべきタスクが開いていれば止める（ignore_blocked で続ける）。
        子タスクの作成元は親のタスクブランチ（GitHubになければ作る。他の base は指定できない）。
        他の人が担当していれば止める（take_over で引き継ぐ）。"""
        return self._repository._start_task_branch(self, base, name=name, ignore_blocked=ignore_blocked,
                                                   take_over=take_over)


@dataclass(frozen=True)
class TaskBranch:
    """タスクブランチ：Issue＋作業用ブランチ task/<番号>-<名前>。コミットはここでだけ行う。"""

    number: int
    branch: str
    base: str
    _repository: "Repository" = field(repr=False, compare=False)

    @property
    def task(self) -> Task:
        return self._repository.task(self.number)

    @property
    def root(self) -> Path:
        """タスクブランチのある場所（task start --dir の作業空間なら、そこ）。"""
        return self._repository.root

    def stage(self, *paths: str, all: bool = False) -> "StageResult":
        repo = self._repository.git
        repo.add(paths, all=all)
        return StageResult(self.branch, repo.working_tree().staged)

    def commit(self, message: str, *, all: bool = False, amend: bool = False) -> "CommitResult":
        repo = self._repository.git
        tree = repo.working_tree()
        if not (amend or repo.is_merging() or tree.staged or (all and tree.unstaged)):
            add = self._repository._op("task add")
            raise WorkError(ErrorCode.NOTHING_TO_COMMIT, "コミットする変更がありません（ステージされていません）。",
                            hint=f"{add} <パス> か {add} --all でステージしてから実行してください"
                                 "（追跡中のファイルの変更だけなら commit --all でも構いません）。")
        if repo.is_merging():
            # 衝突を解決してのコミット（sync continue の代わり）。印が残ったままなら止める。
            self._repository._refuse_conflict_markers(
                repo.conflict_markers("HEAD") if all else repo.conflict_markers(cached=True))
        sha = repo.commit(message, all=all, amend=amend)
        return CommitResult(self.branch, sha, message)

    def record(self, message: str, paths: tuple[str, ...] = (), *, include: "Callable[[str], bool] | None" = None,
               amend: bool = False) -> "RecordResult":
        """変更をコミットする（ステージを意識しない形。task commit）。

        paths なし：追跡中のファイルの変更・削除すべてと、新しいファイルのうち include に当たるもの（None ならすべて）、
        ステージ済みのもの。paths あり：そのパスだけ（新しいファイルも）。衝突の解決中は、登録した内容すべて。
        """
        repo = self._repository.git
        tree = repo.working_tree()
        merging = repo.is_merging()
        if tree.conflicted:
            raise WorkError(ErrorCode.MERGE_CONFLICT, "まだ解決していない衝突があります。",
                            hint=f"ファイルを直して {self._repository._op('sync continue')} で取り込みを完了してください。",
                            details=list(tree.conflicted))
        skipped: tuple[str, ...] = ()
        if paths:
            repo.run("add", "--all", "--", *paths)
        else:
            repo.run("add", "--update")
            new = tuple(p for p in tree.untracked if include is None or include(p))
            skipped = tuple(p for p in tree.untracked if p not in new)
            repo.add(new)
        staged = repo.working_tree().staged
        if not (staged or amend or merging):
            raise WorkError(ErrorCode.NOTHING_TO_COMMIT, "コミットする変更がありません。",
                            hint=("新しいファイルは管理するファイルの対象外のため含めませんでした"
                                  f"（{', '.join(skipped)}）。含めるなら {self._repository._op('task commit')} "
                                  "--message \"…\" <パス>。" if skipped else None),
                            details=list(skipped) or None)
        if merging:
            self._repository._refuse_conflict_markers(repo.conflict_markers(cached=True))
        # --amend でメッセージを省けば、直前のコミットのメッセージのまま
        args = ["commit", "--quiet"] + (["--message", message] if message else ["--no-edit"]) + (
            ["--amend"] if amend else [])
        if paths and not merging:   # 取り込みの途中は一部だけのコミットができない（git の制限）
            args += ["--", *paths]
        repo.run(*args)
        sha = repo.output("rev-parse", "HEAD")
        listed = (("diff", "--name-only", f"{sha}^1", sha) if repo.rev_parse(f"{sha}^1")    # 取り込みは1つ目の親から
                  else ("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha))
        files = tuple(repo.output(*listed).splitlines())
        return RecordResult(self.branch, sha, message or repo.output("log", "-1", "--format=%s"), files, skipped)

    def push(self, *, force: bool = False, dry_run: bool = False) -> "PushResult":
        """GitHubへ送る。commits：送るコミット（新しい順、「短いID 件名」）。dry_run なら送らずに返すだけ。"""
        repo = self._repository.git
        tree = repo.working_tree()
        # GitHubのこのブランチにないもの。まだ送ったことがなければ、GitHubのどのブランチにもないもの
        since = [f"{tree.upstream}..{self.branch}"] if tree.upstream and not tree.upstream_gone else [self.branch, "--not", "--remotes"]
        log = repo.output("log", "--format=%h %s", *since)
        commits = tuple(log.splitlines()) if log else ()
        if not dry_run:
            repo.push(self.branch, set_upstream=tree.upstream is None, force=force)
        return PushResult(self.branch, f"origin/{self.branch}", commits, pushed=not dry_run)

    def submit(self, *, title: str | None = None, partial: bool = False, draft: bool = False,
               reviewers: tuple[str, ...] = ()) -> "PullRequest":
        """提出する（push して作成元へのPRを作る）。提出済みなら送り直し、draft に合わせて下書きを付け外しし、
        title・reviewers を変える。"""
        return self._repository._submit_task_branch(self, title=title, partial=partial, draft=draft,
                                                  reviewers=reviewers)


@dataclass(frozen=True)
class Branch:
    """ブランチ。タスクブランチでないブランチ（main・develop等）の操作に使う。"""

    name: str
    is_task_branch: bool
    base: str | None
    local: bool
    remote: bool
    _repository: "Repository" = field(repr=False, compare=False)
    submission: "PullRequestState | None" = None   # 開いている提出（branch list で分かるとき）
    submitted_to: str | None = None               # その提出の取り込み先

    def submit(self, *, into: str, title: str | None = None, draft: bool = False) -> "PullRequest":
        return self._repository._submit_branch(self, into=into, title=title, draft=draft)

    def delete(self, *, dry_run: bool = False) -> None:
        """dry_runは消せるかを確かめるだけ（消せなければ例外）。"""
        self._repository._delete_branch(self, dry_run=dry_run)


@dataclass(frozen=True)
class PullRequest:
    """PR。値は取得した時点のもの。操作（merge）はPRの番号で、GitHubの最新の内容から判断する。"""

    number: int
    title: str
    url: str
    state: str
    head: str
    base: str
    partial: bool
    _repository: "Repository" = field(repr=False, compare=False)
    author: str = ""
    draft: bool = False

    @classmethod
    def _from(cls, repository: "Repository", info: _github.PullRequestInfo) -> "PullRequest":
        task = task_number(info.head)
        partial = task is not None and task_link(info.body, task) == "refs"
        return cls(info.number, info.title, info.url, info.state, info.head, info.base, partial, repository,
                   info.author, info.draft)

    def merge(self, *, ignore_checks: bool = False) -> "MergeResult":
        """ignore_checks：CIが失敗していてもマージする。"""
        return self._repository._merge_pull_request(self.number, ignore_checks=ignore_checks)


@dataclass(frozen=True)
class StageResult:
    branch: str
    staged: tuple[str, ...]


@dataclass(frozen=True)
class CommitResult:
    branch: str
    sha: str
    message: str


@dataclass(frozen=True)
class RecordResult:
    branch: str
    sha: str
    message: str
    files: tuple[str, ...] = ()       # コミットに入ったファイル
    skipped: tuple[str, ...] = ()     # 含めなかった新しいファイル（管理するファイルの対象外）
    outside: tuple[str, ...] = ()     # パスで指定した、管理するファイルの対象外の新しいファイル（指定どおり含めた）


@dataclass(frozen=True)
class PushResult:
    branch: str
    remote: str
    commits: tuple[str, ...] = ()   # 送る（送った）コミット。新しい順、「短いID 件名」
    pushed: bool = True             # False：dry_run（送っていない）


@dataclass(frozen=True)
class MergeResult:
    number: int
    method: str                      # squash / merge
    closed_issue: int | None
    branch_rebuilt: bool          # --partialの後、タスクブランチを作り直したか
    resumed: bool = False            # マージ済みのPRで、途中で止まった後処理だけを行ったか


@dataclass(frozen=True)
class SkippedBranch:
    branch: str
    reason: str


@dataclass(frozen=True)
class CleanResult:
    removed: tuple[str, ...]
    skipped: tuple[SkippedBranch, ...]
    switched_to: str | None          # 片付けたタスクブランチにいた場合、移った先
    dry_run: bool


@dataclass(frozen=True)
class DropResult:
    number: int
    branch: str
    lost_commits: tuple[str, ...]    # 作成元に入っていないため失われるコミット（件名）
    closed_pull_requests: tuple[int, ...]
    switched_to: str | None          # 今いるタスクブランチを捨てた場合、移った先
    issue_closed: bool               # 「対応しない」として閉じたか
    dry_run: bool


@dataclass(frozen=True)
class PullRequestStatus:
    """PRの状態：内容・レビュー・コメント・CIの結果・マージできるか。"""
    number: int
    title: str
    url: str
    state: str
    head: str
    base: str
    author: str
    draft: bool
    body: str
    task: int | None                 # タスクブランチのPRなら、そのIssueの番号
    activity: _github.PullRequestActivity


@dataclass(frozen=True)
class RemoveResult:
    """手元のタスクブランチを消した結果。GitHubのブランチ・PR・Issueはそのまま。"""
    number: int
    branch: str
    base: str                        # 作成元（Issueに記録済み。再開すると同じ作成元になる）
    remote: bool                     # GitHubにブランチがあるか（なければ再開すると作成元の最新から）
    switched_to: str | None          # 今いるタスクブランチを消した場合、移った先


@dataclass(frozen=True)
class SyncResult:
    branch: str
    merged: tuple[str, ...]          # 取り込んだ（または早送りした）参照。sync continueでは merge／rebase
    extra: object = None             # Hooks.after_sync の戻り値


@dataclass(frozen=True)
class StashResult:
    stashed: bool
    entries: tuple[str, ...]


@dataclass(frozen=True)
class RestoreResult:
    paths: tuple[str, ...]
    staged: bool
    source: str | None = None          # 以前の版の状態に戻したとき：その版（コミット）


@dataclass(frozen=True)
class ResetResult:
    """task reset：タスクブランチを以前の版まで戻した（その後のコミットを捨てた）。"""
    branch: str
    commit: str
    dropped: tuple[tuple[str, str], ...]   # 捨てたコミット（コミット・件名。新しい順）
    dry_run: bool = False
    kept: bool = False                     # 捨てたコミットの変更を、コミットしていない変更として残した（--keep）


@dataclass(frozen=True)
class PullRequestState:
    number: int
    url: str
    state: str
    draft: bool = False
    partial: bool = False            # 中間提出（取り込んでも閉じない）
    base: str = ""                   # 取り込み先のブランチ


@dataclass(frozen=True)
class Status:
    branch: str | None
    task: int | None                   # タスクブランチならIssue番号
    base: str | None
    staged: tuple[str, ...]
    unstaged: tuple[str, ...]
    untracked: tuple[str, ...]
    conflicted: tuple[str, ...]
    ahead: int
    behind: int
    merging: bool
    pull_request: PullRequestState | None
    upstream_gone: bool = False      # GitHubのブランチが削除された（別の場所での反映・中止など）
    reviewing: int | None = None     # task review で確認中のPR
    base_behind: int | None = None   # status --fetch：タスクブランチが作成元より遅れているコミット数
    archived: bool | None = None     # status --fetch：GitHubのリポジトリがアーカイブ（読み取り専用）されている
    reviewing_task: int | None = None   # 確認中の提出のタスク
    finished: bool = False           # タスクブランチのタスクが完了している（GitHubのブランチが消え、Issueが閉じた）
    excluded: tuple[str, ...] = ()   # 新しいファイルのうち、task commit が自動で含めないもの（利用側が決める）
    dependencies: tuple = ()         # 手元の版が記録と違う依存先（利用側が決める）


@dataclass(frozen=True)
class TaskSummary:
    number: int
    title: str
    state: str
    url: str
    task_branch: bool                  # 手元にタスクブランチ（task/<番号>）があるか
    current: bool                    # 今いるタスクブランチか
    remote: bool = False             # GitHubにタスクブランチのブランチがあるか（手元になくても task start で再開できる）
    labels: tuple[str, ...] = ()
    assignees: tuple[str, ...] = ()  # 担当者（ログイン名）
    milestone: str | None = None
    parent: int | None = None        # 親タスク
    subtasks: int = 0                # 子タスクの数
    subtasks_done: int = 0           # そのうち閉じたもの
    blocked_by: int = 0              # 先に終わるべきタスクのうち、開いているものの数
    stage: str | None = None         # 作業の段階（todo・in_progress・in_review・done・planned。未記録ならNone）
    priority: str | None = None
    due: _datetime.date | None = None
    estimate: float | None = None
    sprint: str | None = None
    milestone_due: _datetime.date | None = None
    closed_reason: str | None = None  # completed / not_planned
    planned_start: _datetime.date | None = None   # 開始予定日
    planned_end: _datetime.date | None = None     # 終了予定日
    created: _datetime.date | None = None         # 追加した日
    started: _datetime.date | None = None         # 開始日（初めて作業中になった日）
    finished: _datetime.date | None = None        # 終了日（閉じた日）
    workspace: Path | None = None            # タスクブランチのある手元の場所（このclone。利用側が他のcloneも足す）
    submission: PullRequestState | None = None    # 開いている提出（task list で分かるとき）
    branch: str | None = None                     # タスクブランチの名前（手元かGitHubにあるとき）

    @classmethod
    def _from(cls, task: _model.Task, *, task_branch: bool, current: bool, remote: bool,
              path: Path | None = None, submission: "PullRequestState | None" = None,
              branch: str | None = None) -> "TaskSummary":
        return cls(task.number, task.title, task.state, task.url, task_branch, current, remote, task.labels,
                   task.assignees, task.milestone, task.parent, task.subtasks, task.subtasks_done, task.blocked_by,
                   task.stage, task.priority, task.due, task.estimate,
                   None if task.sprint is None else task.sprint.name, task.milestone_due, task.closed_reason,
                   task.planned_start, task.planned_end, task.created, task.started, task.finished,
                   path if task_branch else None, submission, branch if task_branch or remote else None)


@dataclass(frozen=True)
class TaskStatus:
    """Issue・タスクブランチ・PR（レビュー・コメント・CI）の状態（I-035）。"""
    number: int
    title: str
    state: str
    url: str
    body: str
    task_branch: bool
    base: str | None
    pull_request: PullRequestState | None
    activity: _github.PullRequestActivity | None
    remote: bool = False             # GitHubにタスクブランチのブランチがあるか
    labels: tuple[str, ...] = ()
    assignees: tuple[str, ...] = ()
    comments: tuple[_github.Comment, ...] = ()   # Issueのコメント（作業の記録・申し送り）
    milestone: str | None = None
    parent: "TaskRef | None" = None
    subtasks: tuple["TaskRef", ...] = ()
    blocked_by: tuple["TaskRef", ...] = ()       # 先に終わるべきタスク
    blocking: tuple["TaskRef", ...] = ()         # このタスクを待っているタスク
    task: TaskSummary | None = None              # 段階・計画の値（優先度・期限・見積もり・スプリント等）・日付
    workspace: Path | None = None           # タスクブランチのある手元の場所（TaskSummary と同じ）
    commits: tuple[str, ...] = ()           # 提出に入るコミット（作成元にない、タスクブランチのもの。新しい順、「短いID 件名」）
    branch: str | None = None               # タスクブランチの名前（手元かGitHubにあるとき）


@dataclass(frozen=True)
class ReviewResult:
    number: int                      # 確認するPR
    head: str                        # PRのブランチ
    sha: str
    returned_to: str | None = None   # --done で戻ったブランチ
    task: int | None = None          # タスクブランチの提出なら、そのタスクの番号


@dataclass(frozen=True)
class JudgeResult:
    """差し戻し（task reject）の結果。"""
    task: int
    pull_request: int
    url: str
    returned_to: str | None = None   # 確認中（task review）から戻ったブランチ


@dataclass(frozen=True)
class FinishResult:
    """タスクの完了（task finish・task approve）の結果。"""
    task: int
    pull_request: int                # 取り込んだ提出（PR）
    url: str
    subject: str                     # 取り込んだコミットの件名（(#PR番号) の前）
    partial: bool                    # 中間提出（タスクブランチを作り直して続ける）
    resumed: bool                    # 取り込み済みで、止まっていた後処理だけを行った
    closed_issue: int | None
    branch_rebuilt: bool
    removed: bool                    # 手元のタスクブランチを片付けた
    switched_to: str | None          # 今いたタスクブランチを片付けて移った先
    checks: tuple = ()               # 待ったCIの実行
    next: TaskRef | None = None      # 次のタスクの候補（task next の1番目）
    approved: bool = False           # task approve：承認してから完了した
    returned_to: str | None = None   # task approve：確認中（task review）から戻ったブランチ
    closed_workspace: object = None  # 完了の後に閉じた作業空間（利用側が決める）


@dataclass(frozen=True)
class LogEntry:
    sha: str
    subject: str
    author: str
    date: str
    pull_request: int | None         # 件名の (#N)
    issue: int | None                # そのPRのタスクブランチのIssue


@dataclass(frozen=True)
class RevertResult:
    pull_request: int
    task: int                        # 取り消しの作業を行うタスク（新しく作ったもの）
    branch: str
    sha: str | None                  # 衝突で止まった場合はNone
    reverted_task: int | None = None # task revert：取り消したタスク
