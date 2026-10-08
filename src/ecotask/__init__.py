"""ecotask：GitHubをデータベースとして使うタスク管理のライブラリ。

タスク＝GitHubのIssue。親子（Sub-issues）・依存（Issue dependencies）・マイルストーン・ボード（Projects）も
GitHubの機能をそのまま使い、足りない部分（作業の段階の連動・着手してよいかの判断・名前からIDを引く等）だけを持つ。
git は扱わない（作業空間・PRは ecowork）。gh（GitHub CLI）だけを使う。
"""

from .errors import ErrorCode, TaskError

__version__ = "0.1.0"

__all__ = ["ErrorCode", "TaskError"]
