"""モジュール：ECOBuildの管理単位（GitHubリポジトリ＋CppBuildのSolution）。"""

from __future__ import annotations

import re
from pathlib import Path

from . import _cppbuild, _git, _github
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

    def __repr__(self) -> str:
        return f"Module({self.name!r}, {str(self.root)!r})"
