"""ecoworkは作業の進め方だけを持ち、ECOBuild・CppBuild・CLIを知らない（P-012）。"""

import ast
from pathlib import Path

import ecotask
import ecowork

FORBIDDEN = {"ecobuild", "cppbuild", "cli_framework", "click"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_ecowork_imports_only_itself_and_standard_library():
    sources = sorted(Path(ecowork.__file__).parent.glob("*.py"))
    assert sources
    for path in sources:
        assert not imported_modules(path) & FORBIDDEN, path.name


def test_ecotask_imports_only_itself_and_standard_library():
    """ecotask はタスク管理だけを持ち、作業の流れ（ecowork）も知らない。"""
    sources = sorted(Path(ecotask.__file__).parent.glob("*.py"))
    assert sources
    for path in sources:
        assert not imported_modules(path) & (FORBIDDEN | {"ecowork"}), path.name
