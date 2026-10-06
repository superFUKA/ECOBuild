"""ECOBuild：作業空間（GitHub Issue）を中心にした、モジュールの開発管理の本体。

作業の進め方（作業空間・ブランチ・PR・最新化）はライブラリ ecowork が受け持つ。
言語ごとの処理（ビルド・Project・ファイル・依存先）はモジュールの型が受け持ち、
型は登録ファイル（module_types.toml）に書いたものだけを使う。本体は型の中身（CppBuild等）を知らない。
"""

from ecowork import Branch, PullRequest, Task, Workspace

from .errors import EcoBuildError, ErrorCode
from .module import Module

__version__ = "0.1.0"

__all__ = ["Branch", "EcoBuildError", "ErrorCode", "Module", "PullRequest", "Task", "Workspace"]
