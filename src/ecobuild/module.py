"""モジュール：ECOBuildの管理単位（GitHubリポジトリ＋CppBuildのSolution）。"""

from __future__ import annotations

from pathlib import Path

from . import config as _config


class Module:
    def __init__(self, root: Path, module_config: _config.ModuleConfig):
        self.root = root
        self.config = module_config

    @property
    def name(self) -> str:
        return self.config.name

    @classmethod
    def find(cls, path: Path | str = ".") -> "Module":
        """pathから上へecobuild.tomlを探し、最も近いモジュールを返す（I-027）。"""
        root = _config.find_root(Path(path))
        return cls(root, _config.load(root / _config.FILE_NAME))

    def __repr__(self) -> str:
        return f"Module({self.name!r}, {str(self.root)!r})"
