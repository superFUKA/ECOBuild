"""ECOBuild：GitHubとCppBuildをつなぐ、C++モジュールの開発管理ライブラリ。

公開するのはECOBuildの概念（モジュール・タスク・作業空間・ブランチ・PR）だけ。
git・gh・CppBuildの呼び出しは非公開のモジュール（_git・_github・_cppbuild）に閉じ込めている。
"""

from .errors import EcoBuildError, ErrorCode
from .module import Module
from .workspace import Branch, PullRequest, Task, Workspace

__version__ = "0.1.0"

__all__ = ["Branch", "EcoBuildError", "ErrorCode", "Module", "PullRequest", "Task", "Workspace"]
