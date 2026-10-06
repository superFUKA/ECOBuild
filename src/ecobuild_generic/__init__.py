"""ECOBuildのモジュールの型 generic：ビルド・テスト・実行のコマンドを ecobuild.toml の [commands] に書く。

言語を問わない、いちばん小さな型。作業の流れ（作業空間・PR・CI等）はそのまま使える。
"""

from .type import GenericType

__all__ = ["GenericType"]
