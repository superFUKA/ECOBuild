"""ecowork：Issueを単位にした作業の進め方（作業空間・ブランチ・PR・最新化）のライブラリ。

作業空間＝Issue＝task/<番号> のブランチ。コミットは作業空間でだけ行い、
作業空間でないブランチ（main・develop等）への変更はPRのマージでだけ入る。
git と gh（GitHub CLI）だけを使い、ビルドツールやCLIは持たない。
利用側は Hooks で流れの途中に処理を入れる。
"""

from .errors import ErrorCode, WorkError
from .repository import Hooks, Repository
from .workspace import Branch, PullRequest, Task, Workspace

__version__ = "0.1.0"

__all__ = ["Branch", "ErrorCode", "Hooks", "PullRequest", "Repository", "Task", "WorkError", "Workspace"]
