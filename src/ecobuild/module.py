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

    # 内部 -----------------------------------------------------------------

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
