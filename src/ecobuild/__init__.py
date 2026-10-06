"""ECOBuild：GitHubとCppBuildをつなぐ、C++モジュールの開発管理ライブラリ。

作業の進め方（作業空間・ブランチ・PR・最新化）はライブラリ ecowork が受け持ち、
ECOBuildはそれにCppBuildの処理を組み合わせる。CppBuildの呼び出しは非公開のモジュール（_cppbuild）に閉じ込めている。
"""

from ecowork import Branch, PullRequest, Task, Workspace

from .errors import EcoBuildError, ErrorCode
from .module import Module

__version__ = "0.1.0"

__all__ = ["Branch", "EcoBuildError", "ErrorCode", "Module", "PullRequest", "Task", "Workspace"]
