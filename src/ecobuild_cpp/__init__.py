"""ECOBuildの拡張：型 cpp（C++のモジュールを、CppBuildで管理する）。

本体（ecobuild）の型の口を実装する。使う側が Registry に CppType を登録する（ecobuild_bundle は同梱して登録済み）。
C++だけの操作は cpp(module) から使う：

    cpp(module).set_pch("Core")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .type import CppType

if TYPE_CHECKING:
    from ecobuild import Module

__all__ = ["CppType", "cpp"]


def cpp(module: "Module") -> CppType:
    """module の型 cpp（C++だけの操作の入口）。型が cpp でなければ not_supported。"""
    if not isinstance(module.type, CppType):
        raise module.type.not_supported("C++の操作")
    return module.type
