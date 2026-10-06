"""ECOBuildのモジュールの型 cpp：C++のモジュールを、CppBuildで管理する。

ECOBuildの本体はこの型を直接は使わず、登録ファイル（ecobuild/module_types.toml）を通して読み込む。
"""

from .type import CppType

__all__ = ["CppType"]
