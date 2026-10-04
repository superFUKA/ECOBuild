"""モジュール：ECOBuildの管理単位（GitHubリポジトリ＋CppBuildのSolution）。"""

from __future__ import annotations

import re
from pathlib import Path

from . import _cppbuild, _git, _github
from . import workspace as ws
from . import config as _config
from .errors import EcoBuildError, ErrorCode
from .results import ModuleCreated

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

GITIGNORE = """\
# ECOBuild
/deps/
/build/
ecobuild.local.toml

# CppBuildの中間ファイル・成果物
.cppbuild/output/
"""


class Module:
    def __init__(self, root: Path, module_config: _config.ModuleConfig, *, github: _github.GitHub | None = None):
        self.root = Path(root)
        self.config = module_config
        self._github = github if github is not None else _github.GhCli()
        self._git = _git.Git(self.root)

    @property
    def name(self) -> str:
        return self.config.name

    @classmethod
    def find(cls, path: Path | str = ".", *, github: _github.GitHub | None = None) -> "Module":
        """pathから上へecobuild.tomlを探し、最も近いモジュールを返す（I-027）。"""
        root = _config.find_root(Path(path))
        return cls(root, _config.load(root / _config.FILE_NAME), github=github)

    @classmethod
    def create(
        cls,
        name: str,
        *,
        directory: Path | str = ".",
        description: str = "",
        public: bool = False,
        app: bool = False,
        owner: str | None = None,
        github: _github.GitHub | None = None,
    ) -> "Module":
        """GitHubリポジトリとCppBuildのSolutionを作り、初回コミットをpushする。

        githubは試験でGitHubへの接続を差し替えるためのもの。
        """
        if not _NAME.fullmatch(name):
            raise EcoBuildError(
                ErrorCode.INVALID_CONFIG,
                f"モジュール名 {name!r} は使えません。",
                hint="英字で始まり、英数字と _ だけからなる名前にしてください。",
            )
        root = Path(directory).resolve() / name
        if root.exists():
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{root} は既に存在します。")
        github = github if github is not None else _github.GhCli()
        repository = github.create_repository(name, owner=owner, private=not public, description=description)
        try:
            repo = _git.clone(repository.clone_url, root)
            repo.run("symbolic-ref", "HEAD", "refs/heads/main")
            module_config = _config.ModuleConfig.for_new_module(name, app=app)
            _config.save(module_config, root / _config.FILE_NAME)
            (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8", newline="\n")
            _cppbuild.create_module_solution(root, name, module_config.projects)
            _cppbuild.update(root)
            repo.add(all=True)
            repo.commit("ECOBuildでモジュールを作成")
            repo.push("main", set_upstream=True)
        except EcoBuildError as error:
            error.hint = (error.hint + "\n" if error.hint else "") + (
                f"GitHubのリポジトリ {repository.full_name} は作成済みです。"
                f"やり直す場合は、リポジトリと {root} を削除してから実行してください。"
            )
            raise
        return cls(root, module_config, github=github)

    @property
    def remote_url(self) -> str | None:
        return self._git.get_config("remote.origin.url")

    @property
    def project_names(self) -> tuple[str, ...]:
        projects = self.config.projects
        return tuple(p for p in (projects.library, projects.test, projects.app) if p is not None)

    def summary(self) -> ModuleCreated:
        return ModuleCreated(self.name, self.root, self.remote_url or "", self.project_names)

    # 状態 -----------------------------------------------------------------

    def status(self) -> ws.ModuleStatus:
        tree = self._git.working_tree()
        workspace = self.current_workspace()
        pull_request = None
        if workspace is not None:
            pulls = self._github.pull_requests_for_branch(self.root, workspace.branch)
            if pulls:
                latest = max(pulls, key=lambda p: p.number)
                pull_request = ws.PullRequestState(latest.number, latest.url, latest.state)
        return ws.ModuleStatus(
            branch=tree.branch,
            workspace=None if workspace is None else workspace.number,
            base=None if workspace is None else workspace.base,
            staged=tree.staged, unstaged=tree.unstaged, untracked=tree.untracked, conflicted=tree.conflicted,
            ahead=tree.ahead, behind=tree.behind, merging=self._git.is_merging(), pull_request=pull_request,
        )

    # ブランチ ---------------------------------------------------------------

    def branches(self) -> list[ws.Branch]:
        self._git.fetch()
        local = set(self._git.local_branches())
        remote = set(self._git.remote_branches())
        return [self._branch(name, name in local, name in remote) for name in sorted(local | remote)]

    def branch(self, name: str) -> ws.Branch:
        self._git.fetch()
        local, remote = self._git.has_local_branch(name), self._git.has_remote_branch(name)
        if not (local or remote):
            raise EcoBuildError(ErrorCode.BRANCH_NOT_FOUND, f"ブランチ {name} がありません。")
        return self._branch(name, local, remote)

    def create_branch(self, name: str, *, base: str | None = None) -> ws.Branch:
        """作業空間でないブランチを作り、GitHubへ反映する。"""
        if ws.is_workspace_branch(name):
            raise EcoBuildError(
                ErrorCode.RESERVED_BRANCH_NAME,
                f"{ws.WORKSPACE_PREFIX} で始まる名前は作業空間専用です。",
                hint="作業空間は ecobuild task start <Issue番号> で作ります。",
            )
        start = self._base_start_point(base)
        if self._git.has_local_branch(name) or self._git.has_remote_branch(name):
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"ブランチ {name} は既にあります。")
        self._git.create_branch(name, start, switch=False)
        self._git.push(name, set_upstream=True)
        return self._branch(name, True, True)

    # タスクと作業空間 ---------------------------------------------------------

    def create_task(self, title: str, *, body: str = "") -> ws.Task:
        return ws.Task._from(self, self._github.create_issue(self.root, title, body))

    def task(self, number: int) -> ws.Task:
        return ws.Task._from(self, self._github.get_issue(self.root, number))

    def current_workspace(self) -> ws.Workspace | None:
        branch = self._git.current_branch()
        if branch is None:
            return None
        match = ws._WORKSPACE.fullmatch(branch)
        if match is None:
            return None
        base = self._git.get_config(ws.base_key(branch)) or self.config.default_base
        return ws.Workspace(int(match.group(1)), branch, base, self)

    def require_workspace(self, action: str) -> ws.Workspace:
        workspace = self.current_workspace()
        if workspace is None:
            raise ws.not_in_workspace(action)
        return workspace

    def pull_request(self, number: int | None = None) -> ws.PullRequest:
        """PRを返す。番号を省略すると、今の作業空間の開いているPR。"""
        if number is not None:
            return ws.PullRequest._from(self, self._github.get_pull_request(self.root, number))
        workspace = self.require_workspace("番号を省略したPRの指定")
        pulls = [p for p in self._github.pull_requests_for_branch(self.root, workspace.branch) if p.state == "open"]
        if not pulls:
            raise EcoBuildError(ErrorCode.NO_PULL_REQUEST, f"{workspace.branch} の開いているPRがありません。",
                                hint="ecobuild task submit でPRを作成してください。")
        return ws.PullRequest._from(self, max(pulls, key=lambda p: p.number))

    def clean_workspaces(self, *, dry_run: bool = False) -> ws.CleanResult:
        """Issueが閉じた作業空間のブランチを片付ける。未pushの変更がある作業空間は残す。"""
        self._git.fetch()
        current = self._git.current_branch()
        removed, skipped, switched_to = [], [], None
        for branch in self._git.local_branches():
            match = ws._WORKSPACE.fullmatch(branch)
            if match is None:
                continue
            number = int(match.group(1))
            try:
                issue = self._github.get_issue(self.root, number)
            except EcoBuildError:
                skipped.append(ws.SkippedWorkspace(branch, "Issueを取得できません"))
                continue
            if issue.state != "closed":
                continue
            reason = self._unsafe_to_remove(branch)
            if reason is not None:
                skipped.append(ws.SkippedWorkspace(branch, reason))
                continue
            if dry_run:
                removed.append(branch)
                continue
            if branch == current:
                if not self._git.working_tree().clean:
                    skipped.append(ws.SkippedWorkspace(branch, "今いる作業空間に未コミットの変更があります"))
                    continue
                switched_to = self._git.get_config(ws.base_key(branch)) or self.config.default_base
                self._switch_to_latest(switched_to)
            self._git.delete_branch(branch, force=True)
            if self._git.has_remote_branch(branch):
                self._git.push_delete(branch)
            self._git.unset_config(ws.base_key(branch))
            removed.append(branch)
        return ws.CleanResult(tuple(removed), tuple(skipped), switched_to, dry_run)

    # ビルド ---------------------------------------------------------------

    def project_at(self, path: Path | str) -> str | None:
        """pathが属するProjectの名前。どのProjectにも属さなければNone（全体が対象）。"""
        return _cppbuild.project_at(self.root, Path(path))

    def build(self, *, project: str | None = None, configuration: str = "Debug") -> ws.BuildResult:
        outcome = _cppbuild.build(self.root, project=project, configuration=configuration)
        return ws.BuildResult(project, configuration, tuple(Path(a).as_posix() for a in outcome.artifacts))

    def test(self, *, project: str | None = None, configuration: str = "Debug") -> ws.TestResult:
        outcome = _cppbuild.test(self.root, project=project, configuration=configuration)
        cases = tuple(ws.TestCaseResult(c.name, c.status) for c in outcome.cases)
        count = lambda status: sum(1 for c in cases if c.status == status)  # noqa: E731
        failed = len(cases) - count("passed") - count("skipped")
        return ws.TestResult(project, configuration, count("passed"), failed, count("skipped"), cases)

    def run(self, *, project: str | None = None, configuration: str = "Debug", arguments: str = "") -> ws.RunResult:
        outcome = _cppbuild.run(self.root, project=project, configuration=configuration, arguments=arguments)
        last = outcome.processes[-1] if outcome.processes else None
        return ws.RunResult(project, configuration, 0 if last is None else last.returncode,
                            "" if last is None else last.output)

    # 最新化・退避・取り消し ------------------------------------------------------

    def sync(self) -> ws.SyncResult:
        """GitHubの最新を取り込み、依存先の版と生成ファイルを最新にする。"""
        if self._git.is_merging() or self._git.is_rebasing():
            raise self._in_progress_error()
        branch = self._git.current_branch()
        if branch is None:
            raise EcoBuildError(ErrorCode.GIT_ERROR, "ブランチにいません（切り離された状態です）。")
        self._git.fetch()
        merged = []
        workspace = self.current_workspace()
        refs = [f"{_git.REMOTE}/{branch}"]
        if workspace is not None:
            refs.append(f"{_git.REMOTE}/{workspace.base}")
        for ref in refs:
            if self._git.rev_parse(ref) is None:
                continue
            # 作業空間でないブランチは早送りだけ（コミットはPRのマージでだけ入る）。
            outcome = self._git.merge(ref, ff_only=workspace is None,
                                      message=None if workspace is None else f"{ref} を取り込み")
            if not outcome.merged:
                raise EcoBuildError(
                    ErrorCode.MERGE_CONFLICT,
                    f"{ref} の取り込みで衝突しました。",
                    hint="衝突したファイルを直して ecobuild add で登録し、ecobuild sync --continue"
                         "（または ecobuild commit）で完了してください。やめる場合は ecobuild sync --abort。",
                    details=list(outcome.conflicted),
                )
            if not outcome.already_up_to_date:
                merged.append(ref)
        dependencies: tuple[ws.DependencyChange, ...] = ()
        regenerated = False
        if (self.root / _cppbuild.CONFIG_DIRECTORY).is_dir():
            dependencies = self._sync_dependencies()
            _cppbuild.update(self.root)
            regenerated = True
        return ws.SyncResult(branch, tuple(merged), dependencies, regenerated)

    def continue_sync(self) -> ws.SyncResult:
        """衝突を解決した後、止まっている取り込み（または作業空間の作り直し）を完了する。"""
        branch = self._git.current_branch() or ""
        if self._git.is_rebasing():
            outcome = self._git.rebase_continue()
            if not outcome.merged:
                raise EcoBuildError(ErrorCode.MERGE_CONFLICT, "続きの載せ替えで衝突しました。",
                                    hint="ファイルを直して ecobuild add で登録し、もう一度 ecobuild sync --continue。",
                                    details=list(outcome.conflicted))
            branch = self._git.current_branch() or branch
            return ws.SyncResult(branch, ("rebase",), (), False)
        if self._git.is_merging():
            self._git.merge_continue()
            return ws.SyncResult(branch, ("merge",), (), False)
        raise EcoBuildError(ErrorCode.NO_SYNC_IN_PROGRESS, "止まっている取り込みはありません。")

    def abort_sync(self) -> None:
        if self._git.is_rebasing():
            self._git.rebase_abort()
        elif self._git.is_merging():
            self._git.merge_abort()
        else:
            raise EcoBuildError(ErrorCode.NO_SYNC_IN_PROGRESS, "止まっている取り込みはありません。")

    def stash(self) -> ws.StashResult:
        stashed = self._git.stash_push()
        return ws.StashResult(stashed, self._stash_messages())

    def stash_pop(self) -> ws.StashResult:
        if not self._git.stash_list():
            raise EcoBuildError(ErrorCode.NO_SYNC_IN_PROGRESS, "退避した変更はありません。")
        outcome = self._git.stash_pop()
        if not outcome.merged:
            raise EcoBuildError(ErrorCode.MERGE_CONFLICT, "退避した変更を戻すときに衝突しました。",
                                hint="衝突したファイルを直して ecobuild add で登録してください"
                                     "（退避した変更は ecobuild stash list に残っています）。",
                                details=list(outcome.conflicted))
        return ws.StashResult(True, self._stash_messages())

    def stashes(self) -> tuple[str, ...]:
        return self._stash_messages()

    def restore(self, *paths: str, staged: bool = False) -> ws.RestoreResult:
        self._git.restore(paths, staged=staged)
        return ws.RestoreResult(paths, staged)

    # 内部 -----------------------------------------------------------------

    def _stash_messages(self) -> tuple[str, ...]:
        return tuple(entry.message for entry in self._git.stash_list())

    def _in_progress_error(self) -> EcoBuildError:
        return EcoBuildError(
            ErrorCode.MERGE_CONFLICT,
            "前回の取り込みが衝突で止まっています。",
            hint="ファイルを直して ecobuild add で登録し、ecobuild sync --continue で続けるか、"
                 "ecobuild sync --abort でやめてください。",
            details=list(self._git.working_tree().conflicted),
        )

    def _sync_dependencies(self) -> tuple[ws.DependencyChange, ...]:
        """依存先を記録の版に合わせる。手元で変更・コミットしているものは触らない。"""
        fetched, sources = _cppbuild.fetch_dependencies(self.root)
        changes = []
        for source in sources:
            if source.name in fetched:
                changes.append(ws.DependencyChange(source.name, "cloned"))
                continue
            clone = _git.Git(source.directory)
            head = clone.rev_parse("HEAD")
            if head == source.revision:
                changes.append(ws.DependencyChange(source.name, "unchanged"))
                continue
            if not clone.working_tree().clean:
                changes.append(ws.DependencyChange(source.name, "skipped", "未コミットの変更があります"))
                continue
            clone.fetch()
            if not clone.output("branch", "--remotes", "--contains", head):
                changes.append(ws.DependencyChange(source.name, "skipped", "GitHubにないコミットがあります"))
                continue
            clone.run("switch", "--quiet", "--detach", source.revision)
            changes.append(ws.DependencyChange(source.name, "aligned"))
        return tuple(changes)

    def _unsafe_to_remove(self, branch: str) -> str | None:
        """消すと失われるコミットがあれば理由を返す。"""
        tip = self._git.rev_parse(branch)
        if self._git.has_remote_branch(branch) and self._git.is_ancestor(tip, f"{_git.REMOTE}/{branch}"):
            return None
        merged_heads = [p.head_sha for p in self._github.pull_requests_for_branch(self.root, branch)
                        if p.state == "merged" and p.head_sha]
        if any(self._git.rev_parse(sha) and self._git.is_ancestor(tip, sha) for sha in merged_heads):
            return None
        return "GitHubにないコミットがあります"

    def _switch_to_latest(self, name: str) -> None:
        if self._git.has_local_branch(name):
            self._git.switch(name)
            if self._git.has_remote_branch(name):
                self._git.merge(f"{_git.REMOTE}/{name}", ff_only=True)
        else:
            self._git.create_branch(name, f"{_git.REMOTE}/{name}", switch=True)
            self._git.set_upstream(name)

    def _check_generated_files(self) -> None:
        """CppBuildで生成し直し、生成・管理ファイルに未コミットの変更があれば止める。"""
        if not (self.root / _cppbuild.CONFIG_DIRECTORY).is_dir():
            return
        _cppbuild.update(self.root)
        tree = self._git.working_tree()
        changed = sorted({p for p in (*tree.staged, *tree.unstaged, *tree.untracked)
                          if _cppbuild.is_generated_or_managed(p)})
        if changed:
            raise EcoBuildError(
                ErrorCode.GENERATED_FILES_OUTDATED,
                "CppBuildの生成ファイル・管理ファイルがコミットされていません。",
                hint="ecobuild add --all でステージし、ecobuild commit でコミットしてから再実行してください。",
                details=changed,
            )

    def _submit_workspace(self, workspace: ws.Workspace, *, title: str | None, partial: bool) -> ws.PullRequest:
        self._check_generated_files()
        self._git.fetch()
        base_ref = f"{_git.REMOTE}/{workspace.base}"
        if self._git.count(f"{base_ref}..{workspace.branch}") == 0:
            raise EcoBuildError(ErrorCode.NOTHING_TO_SUBMIT, f"{workspace.base} へ反映するコミットがありません。",
                                hint="変更をコミットしてから再実行してください。")
        workspace.push()
        opened = [p for p in self._github.pull_requests_for_branch(self.root, workspace.branch) if p.state == "open"]
        if opened:
            # 既にあるPRには、pushしたコミットがそのまま加わる。
            return ws.PullRequest._from(self, max(opened, key=lambda p: p.number))
        issue = self._github.get_issue(self.root, workspace.number)
        keyword = "Refs" if partial else "Closes"
        info = self._github.create_pull_request(
            self.root, head=workspace.branch, base=workspace.base,
            title=title or issue.title, body=f"{keyword} #{workspace.number}\n",
        )
        return ws.PullRequest._from(self, info)

    def _submit_branch(self, branch: ws.Branch, *, into: str, title: str | None) -> ws.PullRequest:
        if branch.is_workspace:
            raise EcoBuildError(ErrorCode.PROTECTED_BRANCH, f"{branch.name} は作業空間です。",
                                hint="作業空間の反映は ecobuild task submit で行います。")
        self._git.fetch()
        for name in (branch.name, into):
            if not self._git.has_remote_branch(name):
                raise EcoBuildError(ErrorCode.BRANCH_NOT_FOUND, f"GitHubにブランチ {name} がありません。")
        if self._git.count(f"{_git.REMOTE}/{into}..{_git.REMOTE}/{branch.name}") == 0:
            raise EcoBuildError(ErrorCode.NOTHING_TO_SUBMIT, f"{branch.name} から {into} へ反映するコミットがありません。")
        info = self._github.create_pull_request(
            self.root, head=branch.name, base=into, title=title or f"{branch.name} を {into} へ反映", body="",
        )
        return ws.PullRequest._from(self, info)

    def _merge_pull_request(self, pr: ws.PullRequest) -> ws.MergeResult:
        current = self._github.get_pull_request(self.root, pr.number)
        if current.state != "open":
            raise EcoBuildError(ErrorCode.PULL_REQUEST_NOT_OPEN, f"PR #{pr.number} は開いていません（{current.state}）。")
        match = ws._WORKSPACE.fullmatch(pr.head)
        if match is None:
            # ブランチ同士はマージコミットで履歴を残す。
            self._github.merge_pull_request(self.root, pr.number, squash=False, subject=None)
            return ws.MergeResult(pr.number, "merge", None, False)
        number = int(match.group(1))
        self._github.merge_pull_request(self.root, pr.number, squash=True, subject=f"{pr.title} (#{pr.number})")
        if pr.partial:
            rebuilt = self._rebuild_workspace(pr.head, current.head_sha)
            return ws.MergeResult(pr.number, "squash", None, rebuilt)
        if self._github.get_issue(self.root, number).state == "open":
            self._github.close_issue(self.root, number)
        self._git.fetch()
        if self._git.has_remote_branch(pr.head):
            self._git.push_delete(pr.head)
        return ws.MergeResult(pr.number, "squash", number, False)

    def _rebuild_workspace(self, branch: str, merged_head: str | None) -> bool:
        """--partialのPRをsquashマージした後、作業空間を作成元の最新から作り直す。

        PRに含まれなかった続きのコミットは載せ替える（git rebase --onto と同じ）。
        """
        if merged_head is None or not self._git.has_local_branch(branch):
            return False
        self._git.fetch()
        base = self._git.get_config(ws.base_key(branch)) or self.config.default_base
        previous = self._git.current_branch()
        outcome = self._git.rebase_onto(f"{_git.REMOTE}/{base}", merged_head, branch)
        if not outcome.merged:
            raise EcoBuildError(
                ErrorCode.MERGE_CONFLICT,
                "作業空間の作り直しで衝突しました。",
                hint="ファイルを直して ecobuild add で登録し、ecobuild sync --continue で続けてください"
                     "（やめる場合は ecobuild sync --abort）。",
                details=list(outcome.conflicted),
            )
        self._git.push(branch, force=True)
        if previous is not None and previous != branch:
            self._git.switch(previous)  # rebaseで移った作業空間から、元のブランチへ戻る
        return True

    def _branch(self, name: str, local: bool, remote: bool) -> ws.Branch:
        is_workspace = ws.is_workspace_branch(name)
        base = self._git.get_config(ws.base_key(name)) if is_workspace else None
        return ws.Branch(name, is_workspace, base, local, remote, self)

    def _base_start_point(self, base: str | None) -> str:
        """作成元のブランチを確かめ、GitHubの最新を起点として返す。"""
        base = base or self.config.default_base
        if ws.is_workspace_branch(base):
            raise EcoBuildError(
                ErrorCode.INVALID_BASE,
                f"作業空間 {base} は作成元にできません。",
                hint="作業空間でないブランチ（main・develop等）を指定してください。",
            )
        self._git.fetch()
        if self._git.has_remote_branch(base):
            return f"{_git.REMOTE}/{base}"
        if self._git.has_local_branch(base):
            return base
        raise EcoBuildError(ErrorCode.BRANCH_NOT_FOUND, f"作成元のブランチ {base} がありません。")

    def _delete_branch(self, branch: ws.Branch) -> None:
        if branch.is_workspace:
            raise EcoBuildError(ErrorCode.PROTECTED_BRANCH, f"{branch.name} は作業空間です。",
                                hint="作業空間は ecobuild task clean で片付けます。")
        protected = {self.config.default_base, self._github.default_branch(self.root)}
        if branch.name in protected:
            raise EcoBuildError(ErrorCode.PROTECTED_BRANCH, f"{branch.name} は既定のブランチなので消せません。")
        users = [name for name in self._git.local_branches()
                 if ws.is_workspace_branch(name) and self._git.get_config(ws.base_key(name)) == branch.name]
        if users:
            raise EcoBuildError(ErrorCode.PROTECTED_BRANCH,
                                f"{branch.name} は作業空間（{', '.join(users)}）の作成元なので消せません。",
                                hint="先に作業空間を片付けてください（ecobuild task clean）。")
        if self._git.current_branch() == branch.name:
            raise EcoBuildError(ErrorCode.PROTECTED_BRANCH, f"今いるブランチ {branch.name} は消せません。",
                                hint="別のブランチへ移ってから実行してください。")
        if branch.local:
            self._git.delete_branch(branch.name, force=True)
        if branch.remote:
            self._git.push_delete(branch.name)

    def _start_workspace(self, task: ws.Task, base: str | None) -> ws.Workspace:
        if task.state != "open":
            raise EcoBuildError(ErrorCode.TASK_NOT_FOUND, f"Issue #{task.number} は閉じています。",
                                hint="作業を再開するには、GitHubでIssueを開き直してください。")
        if not self._git.working_tree().clean:
            raise EcoBuildError(
                ErrorCode.DIRTY_WORKING_TREE,
                "未コミットの変更があるため、作業空間を作れません（別のIssueの作業に混ざるのを防ぐため）。",
                hint="変更をコミットするか、ecobuild stash で退避してから実行してください。",
            )
        branch = ws.workspace_branch(task.number)
        if self._git.has_local_branch(branch):
            # 既にある作業空間へ戻る
            self._git.switch(branch)
        else:
            start = self._base_start_point(base)
            if self._git.has_remote_branch(branch):
                start = f"{_git.REMOTE}/{branch}"
            self._git.create_branch(branch, start, switch=True)
            self._git.set_config(ws.base_key(branch), (base or self.config.default_base))
            if self._git.has_remote_branch(branch):
                self._git.set_upstream(branch)
        workspace = self.current_workspace()
        assert workspace is not None
        return workspace

    def __repr__(self) -> str:
        return f"Module({self.name!r}, {str(self.root)!r})"
