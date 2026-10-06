"""モジュールの型の登録：本体は型の中身（CppBuild等）を知らず、登録ファイルの型だけを使う。"""

import ast
from pathlib import Path

import pytest

import ecobuild
from ecobuild import module_type
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.module_type import ModuleType, TypeEntry


def test_core_does_not_import_cppbuild():
    """本体（ecobuild）のどのファイルも cppbuild・ecobuild_cpp を import しない（型は登録ファイル経由）。"""
    root = Path(ecobuild.__file__).parent
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(n.split(".")[0] in ("cppbuild", "ecobuild_cpp") for n in names), path


def test_registry_lists_cpp():
    entries = module_type.entries()
    assert entries["cpp"].module == "ecobuild_cpp" and entries["cpp"].cls == "CppType"
    assert module_type.load("cpp").name == "cpp"
    with pytest.raises(EcoBuildError) as error:
        module_type.load("nosuch")
    assert error.value.code == ErrorCode.INVALID_CONFIG and "cpp" in error.value.hint


class PlainType(ModuleType):
    """何にも対応しない型（試験用）。"""
    name = "plain"


def test_unsupported_operations_are_reported(monkeypatch, module):
    """型が対応しない操作は not_supported で止まる。作業の流れ（ecowork）はそのまま使える。"""
    monkeypatch.setattr(module_type, "entries", lambda: {"plain": TypeEntry("plain", __name__, "PlainType", "")})
    module.type = module_type.load("plain")(module)
    for action in (lambda: module.build(), lambda: module.test(), lambda: module.projects()):
        with pytest.raises(EcoBuildError) as error:
            action()
        assert error.value.code == ErrorCode.NOT_SUPPORTED and "plain" in error.value.message
    workspace = module.create_task("型に関係なく使える").start()
    assert module.current_workspace().number == workspace.number
    with pytest.raises(EcoBuildError) as error:
        module.add_file("x.txt")
    assert error.value.code == ErrorCode.NOT_SUPPORTED
    assert module.dependencies() == () and module.sync().merged == ()
