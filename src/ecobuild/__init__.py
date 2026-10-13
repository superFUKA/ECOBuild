"""ECOBuild の本体（ライブラリ）：作業空間（GitHub Issue）を中心にした、モジュールの開発管理。

作業の進め方（作業空間・ブランチ・PR・最新化）はライブラリ ecowork が受け持つ。
言語ごとの処理（ビルド・Project・ファイル・依存先）はモジュールの型が受け持つ。本体は型の中身を知らず、
使う側が型を Registry に登録して Module に渡す（外部から型を足せる）。CLI・拡張（CppBuild等）は知らない。

    registry = Registry([MyType], default="mine")
    module = Module.find(".", registry=registry)
"""

from ecowork import Branch, PullRequest, Task, Workspace

from .errors import EcoBuildError, ErrorCode
from .module import Module
from .module_type import Builds, HasDependencies, HasFiles, HasProjects, ModuleType, Registry, TypeEntry

__version__ = "0.1.0"

__all__ = ["Branch", "Builds", "EcoBuildError", "ErrorCode", "HasDependencies", "HasFiles", "HasProjects", "Module",
           "ModuleType", "PullRequest", "Registry", "Task", "TypeEntry", "Workspace"]
