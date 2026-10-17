"""ecowork：Issueを単位にした作業の進め方（タスクブランチ・ブランチ・PR・最新化）のライブラリ。

タスクブランチ＝Issue＝task/<番号> のブランチ。コミットはタスクブランチでだけ行い、
タスクブランチでないブランチ（main・develop等）への変更はPRのマージでだけ入る。
git と gh（GitHub CLI）だけを使い、ビルドツールやCLIは持たない。
利用側は Hooks で流れの途中に処理を入れる。

タスク管理（ecotask）の上に作る：タスクブランチはタスク（Issue）に結び付き、例外も ecotask と同じ1つの型（WorkError は
ecotask.TaskError。層ごとにエラーの種類〔ErrorCode〕だけを足す）。利用側（ecobuild）は ecotask を直接使わず、
必要なものはここ（と ecowork.github・ecowork.process）から使う。
"""

from .errors import ErrorCode, WorkError
from .repository import Hooks, Repository
from .model import Branch, PullRequest, Task, TaskRef, TaskBranch

__version__ = "0.1.0"

__all__ = ["Branch", "ErrorCode", "Hooks", "PullRequest", "Repository", "Task", "TaskRef", "WorkError", "TaskBranch"]
