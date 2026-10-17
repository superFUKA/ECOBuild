"""Repository の一部：CI（GitHub Actions）。

Repository（repository.py）がこのクラスを継承する。self は Repository。
"""

from __future__ import annotations

import time
from collections.abc import Callable

from . import git as _git
from . import github as _github
from . import model as wm
from .errors import ErrorCode, WorkError


class Ci:
    # CI（GitHub Actions） ----------------------------------------------------------

    def ci_runs(self, *, pull_request: int | None = None, limit: int = 5, task: int | None = None) -> list:
        """今いるブランチ（またはPR・タスクのタスクブランチのブランチ）のCIの実行（新しい順）。"""
        branch = self._ci_branch(pull_request, task)
        return self.github.list_runs(self.root, branch=branch, limit=limit)

    def ci_failed_log(self, run_id: int | None = None, *, task: int | None = None) -> tuple[int, str]:
        """失敗した手順のログ。run_idを省略すると、今いるブランチ（task：そのタスクブランチ）の最新の失敗した実行。"""
        if run_id is None:
            failed = [r for r in self.github.list_runs(self.root, branch=self._ci_branch(None, task), limit=20)
                      if _github.ci_result(r.status, r.conclusion) == _github.FAILED]
            if not failed:
                raise WorkError(ErrorCode.NO_CI_RUN, "失敗したCIの実行はありません。",
                                hint=f"{self._op('ci status')} で実行の一覧を確認できます。")
            run_id = failed[0].id
        return run_id, self.github.failed_log(self.root, run_id)

    def ci_rerun(self, run_id: int | None = None, *, failed_only: bool = False, task: int | None = None) -> int:
        """CIをもう一度実行する。run_idを省略すると、今いるブランチ（task：そのタスクブランチ）の最新の実行。"""
        if run_id is None:
            runs = self.github.list_runs(self.root, branch=self._ci_branch(None, task), limit=1)
            if not runs:
                raise WorkError(ErrorCode.NO_CI_RUN, "このブランチのCIの実行はありません。",
                                hint=f"{self._op('ci run')} で手動で実行できます（pushしてから）。")
            run_id = runs[0].id
        self.github.rerun(self.root, run_id, failed_only=failed_only)
        return run_id

    def ci_dispatch(self, workflow: str) -> str:
        """今いるブランチで、CIを手動で実行する（GitHubにあるブランチの内容で動く）。"""
        branch = self._ci_branch(None)
        self.git.fetch()
        if not self.git.has_remote_branch(branch):
            raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"GitHubにブランチ {branch} がありません。",
                            hint=f"{self._op('task push')} してから実行してください。")
        self.github.dispatch(self.root, workflow, ref=branch)
        return branch

    def ci_wait(self, pull_request: int | None = None, *, timeout: float = 1800, interval: float = 15,
                start_grace: float = 120, sleep: Callable[[float], None] = time.sleep,
                clock: Callable[[], float] = time.monotonic, task: int | None = None) -> list:
        """GitHubにある最新のコミット（今いるブランチ、またはPR）のCIが終わるまで待ち、実行を返す。

        失敗があれば checks_failed、時間内に終わらなければ checks_pending。push の直後は実行が現れるまで
        start_grace 秒待ち、現れなければ no_ci_run。
        """
        if pull_request is None and task is not None:
            submitted = self.submission(task)
            pull_request = None if submitted is None else submitted.number
        if pull_request is not None:
            pr = self.github.get_pull_request(self.root, pull_request)
            branch, sha = pr.head, pr.head_sha
        else:
            branch = self._ci_branch(None, task)
            self.git.fetch()
            sha = self.git.rev_parse(f"{_git.REMOTE}/{branch}")
            if sha is None:
                raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"GitHubにブランチ {branch} がありません。",
                                hint=f"{self._op('task push')} してから実行してください。")
        started = clock()
        while True:
            runs = [r for r in self.github.list_runs(self.root, branch=branch, limit=20) if r.head_sha == sha]
            elapsed = clock() - started
            results = [_github.ci_result(r.status, r.conclusion) for r in runs]
            if runs and _github.PENDING not in results:
                failed = [r for r, result in zip(runs, results) if result == _github.FAILED]
                if failed:
                    raise WorkError(ErrorCode.CHECKS_FAILED,
                                    f"{branch} のCIが失敗しました：" + ", ".join(f"#{r.id} {r.workflow}" for r in failed),
                                    hint=f"{self._op('ci logs')} で失敗した手順のログを確認できます。",
                                    details=[{"id": r.id, "workflow": r.workflow, "conclusion": r.conclusion,
                                              "url": r.url} for r in failed])
                return runs
            if not runs and elapsed >= min(start_grace, timeout):
                raise WorkError(ErrorCode.NO_CI_RUN, f"{branch} の最新のコミット（{(sha or '')[:7]}）のCIの実行がありません。",
                                hint=f"CIがなければ {self._op('ci init')} で用意できます。手動で動かすなら {self._op('ci run')}。")
            if elapsed >= timeout:
                raise WorkError(ErrorCode.CHECKS_PENDING, f"{branch} のCIが {int(timeout)} 秒で終わりませんでした。",
                                hint=f"もう一度 {self._op('ci wait')} で待つか、{self._op('ci status')} で確認してください。",
                                details=[{"id": r.id, "workflow": r.workflow, "status": r.status} for r in runs])
            sleep(interval)

    def delete_secret(self, name: str) -> str:
        self.github.delete_secret(self.root, name)
        return name

    def set_secret(self, name: str, value: str) -> str:
        if not name or not value:
            raise WorkError(ErrorCode.INVALID_ARGUMENT, "シークレットの名前と値が必要です。")
        self.github.set_secret(self.root, name, value)
        return name

    def secrets(self) -> list[str]:
        return self.github.list_secrets(self.root)

    def _has_workflows(self) -> bool:
        """GitHub Actions のワークフローがあるか（あればPRにCIの結果が付くはず）。"""
        directory = self.root / ".github" / "workflows"
        return directory.is_dir() and (any(directory.glob("*.yml")) or any(directory.glob("*.yaml")))

    def _ci_branch(self, pull_request: int | None, task: int | None = None) -> str:
        if pull_request is not None:
            return self.github.get_pull_request(self.root, pull_request).head
        if task is not None:
            return wm.task_branch_name(task)
        branch = self.git.current_branch()
        if branch is None:
            raise WorkError(ErrorCode.GIT_ERROR, "ブランチにいません（切り離された状態です）。",
                            hint="--task でタスクの番号を指定してください。")
        return branch
