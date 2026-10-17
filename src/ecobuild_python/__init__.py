"""ECOBuildのモジュールの型 python：venv・pip・pytest でビルド・テスト・実行・ファイルの追加を行う。

Project・依存先の管理は持たない。作業の流れ（タスクブランチ・PR・CI等）はそのまま使える。
"""

from .type import PythonType

__all__ = ["PythonType"]
