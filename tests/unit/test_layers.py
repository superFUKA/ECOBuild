"""層の境目：本体 → 拡張 → 本体＋拡張 → CLI の順に積み、下の層は上の層を import しない。"""

import ast
import importlib
from pathlib import Path

import pytest

# パッケージ → import してはいけないもの（パッケージの先頭の名前）
FORBIDDEN = {
    "ecobuild": {"ecobuild_bundle", "ecobuild_cli", "ecobuild_cpp", "ecobuild_generic", "ecobuild_python", "cppbuild",
                 "click", "cli_framework"},
    "ecobuild_cpp": {"ecobuild_bundle", "ecobuild_cli", "ecobuild_generic", "ecobuild_python", "click", "cli_framework"},
    "ecobuild_generic": {"ecobuild_bundle", "ecobuild_cli", "ecobuild_cpp", "ecobuild_python", "cppbuild", "click",
                         "cli_framework"},
    "ecobuild_python": {"ecobuild_bundle", "ecobuild_cli", "ecobuild_cpp", "ecobuild_generic", "cppbuild", "click",
                        "cli_framework"},
    "ecobuild_bundle": {"ecobuild_cli", "click", "cli_framework"},
}


def _imports(path: Path, package: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_lower_layers_do_not_import_upper_layers(package):
    root = Path(importlib.import_module(package).__file__).parent
    for path in root.rglob("*.py"):
        found = _imports(path, package) & FORBIDDEN[package]
        assert not found, f"{path.relative_to(root.parent)} が {sorted(found)} を import しています"
