"""Repository の一部：履歴・取り消し・その他。

Repository（repository.py）がこのクラスを継承する。self は Repository。
"""

from __future__ import annotations

from . import git as _git
from . import model as wm
from .errors import ErrorCode, WorkError
from ._shared import _PR_IN_SUBJECT


class History:
    # 履歴・取り消し・その他 -----------------------------------------------------------

    def log(self, *, count: int = 20, paths: tuple[str, ...] = (), all_branches: bool = False) -> list[wm.LogEntry]:
        """履歴。件名の (#N) からPRを、そのPRのタスクブランチからIssueを添える。"""
        args = ["log", f"--max-count={count}", "--format=%H%x1f%s%x1f%an%x1f%ad", "--date=iso-strict"]
        if all_branches:
            args.append("--all")
        rows = [line.split("\x1f") for line in self.git.output(*args, "--", *paths).splitlines()]
        matches = [_PR_IN_SUBJECT.search(row[1]) for row in rows]
        pull_issue = {}
        if any(matches):
            pull_issue = {p.number: wm.task_number(p.head) for p in self.github.merged_pull_requests(self.root)}
        entries = []
        for match, (sha, subject, author, date) in zip(matches, rows):
            pr = int(match.group(1)) if match else None
            entries.append(wm.LogEntry(sha, subject, author, date, pr, pull_issue.get(pr)))
        return entries

    def show(self, revision: str = "HEAD") -> str:
        return self.git.output("show", "--stat", "--patch", revision)

    def diff(self, paths: tuple[str, ...] = (), *, staged: bool = False, base: bool = False) -> str:
        """未コミットの変更の差分。staged：ステージ済みだけ。base：タスクブランチの作成元との差分（PRの差分）。"""
        args = ["diff"]
        if base:
            task_branch = self.require_task_branch("作成元との差分")
            self.git.fetch()
            args.append(f"{_git.REMOTE}/{task_branch.base}...HEAD")
        elif staged:
            args.append("--cached")
        return self.git.output(*args, "--", *paths)

    def blame(self, path: str) -> str:
        return self.git.output("blame", "--date=short", "--", path)

    def revert(self, number: int) -> wm.RevertResult:
        """マージ済みのPRを取り消すタスクブランチを作る（Issue作成→タスクブランチ→取り消しのコミット）。PRは task submit で出す。"""
        pr = self.github.get_pull_request(self.root, number)
        if pr.state != "merged" or not pr.merge_commit:
            raise WorkError(ErrorCode.PULL_REQUEST_NOT_OPEN, f"PR #{number} はマージされていません（{pr.state}）。",
                            hint="取り消せるのはマージ済みのPRだけです。")
        return self._revert([pr], f"「{pr.title}」を取り消す", f"#{number} を取り消す。\n")

    def _revert(self, pulls: list, title: str, body: str, *, task: int | None = None) -> wm.RevertResult:
        """取り込んだPR（古い順）を、新しいものから順に取り消すコミットを、新しいタスクのタスクブランチに作る。"""
        created = self.create_task(title, body=body)
        task_branch = created.start(base=pulls[-1].base)
        self.git.fetch()
        for pr in reversed(pulls):
            parents = self.git.output("rev-list", "--parents", "-n", "1", pr.merge_commit).split()
            args = ["revert", "--no-edit"] + (["-m", "1"] if len(parents) > 2 else []) + [pr.merge_commit]
            completed = self.git.run(*args, check=False)
            if not completed.ok:
                conflicted = self.git.working_tree().conflicted
                if conflicted:
                    raise WorkError(ErrorCode.MERGE_CONFLICT, "取り消しで衝突しました。",
                                    hint=f"タスクブランチ {task_branch.branch} で、衝突したファイルを直して "
                                         f"{self._op('task commit')} --message で記録してください。",
                                    details=list(conflicted))
                raise _git._git_error(completed)
        self.hooks.after_switch(self)  # 取り消しで依存先の記録等が戻ることがある
        return wm.RevertResult(pulls[-1].number, created.number, task_branch.branch, self.git.output("rev-parse", "HEAD"),
                               reverted_task=task)

    def ignore(self, *patterns: str) -> tuple[str, ...]:
        """.gitignore に追加する（既にあるものは足さない）。足したものを返す。タスクブランチでだけ。"""
        self.require_task_branch("管理から外すファイルの指定")
        path = self.root / ".gitignore"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        existing = {line.strip() for line in text.splitlines()}
        added = tuple(dict.fromkeys(p for p in patterns if p.strip() and p.strip() not in existing))
        if added:
            prefix = "" if not text or text.endswith("\n") else "\n"
            path.write_text(text + prefix + "\n".join(added) + "\n", encoding="utf-8", newline="\n")
        return added

    def create_release(self, tag: str, *, title: str = "", notes: str = "", target: str | None = None):
        """リリースを作る。タグを付けられるのはタスクブランチでないブランチ（PRで反映済みの内容）だけ。"""
        target = target or self.default_base
        if wm.is_task_branch(target):
            raise WorkError(ErrorCode.INVALID_BASE, f"タスクブランチ {target} にはリリースのタグを付けられません。",
                            hint="PRで反映した、タスクブランチでないブランチ（main・develop等）を指定してください。")
        return self.github.create_release(self.root, tag=tag, title=title, notes=notes, target=target)

    def releases(self):
        return self.github.list_releases(self.root)
