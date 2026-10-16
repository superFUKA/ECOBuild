"""層の境目：本体 → 拡張 → 本体＋拡張 → CLI の順に積み、下の層は上の層を import しない。

型の拡張の cli パッケージ（ecobuild_<型>.cli）は、その型のコマンド＝CLI の層。ecobuild_cli の公開の補助
（ecobuild_cli.kit）だけを使い、click・CLIFrameWork は使わない。型の本体は cli を import しない。
"""

import ast
import importlib
from pathlib import Path

import pytest

TYPES = ("ecobuild_cpp", "ecobuild_generic", "ecobuild_python")

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
    # CLI は型を知らない（型のコマンドは登録した型の cli パッケージを名前で読み込む）
    "ecobuild_cli": {"ecobuild_cpp", "ecobuild_generic", "ecobuild_python", "cppbuild"},
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module)
            elif node.level and (node.module or "").split(".")[0] == "cli":
                names.add(".cli")
            elif node.level and any(a.name == "cli" for a in node.names):
                names.add(".cli")
    return names


def _imports(path: Path) -> set[str]:
    return {name.split(".")[0] for name in _imported_modules(path)}


def _root(package: str) -> Path:
    return Path(importlib.import_module(package).__file__).parent


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_lower_layers_do_not_import_upper_layers(package):
    root = _root(package)
    for path in root.rglob("*.py"):
        if package in TYPES and "cli" in path.relative_to(root).parts[:1]:
            continue          # 型のコマンド（CLI の層）は下で確かめる
        found = _imports(path) & FORBIDDEN[package]
        assert not found, f"{path.relative_to(root.parent)} が {sorted(found)} を import しています"
        if package in TYPES:
            assert ".cli" not in _imported_modules(path) and f"{package}.cli" not in _imported_modules(path), \
                f"{path.relative_to(root.parent)} が型のコマンド（cli）を import しています"


@pytest.mark.parametrize("package", TYPES)
def test_type_commands_use_only_the_public_cli_helpers(package):
    root = _root(package) / "cli"
    others = set(TYPES) - {package}
    for path in root.rglob("*.py"):
        modules = _imported_modules(path)
        found = {name.split(".")[0] for name in modules} & ({"click", "cli_framework", "cppbuild"} | others)
        assert not found, f"{path.relative_to(root.parent.parent)} が {sorted(found)} を import しています"
        private = {name for name in modules if name.startswith("ecobuild_cli") and name != "ecobuild_cli.kit"}
        assert not private, f"{path.relative_to(root.parent.parent)} が {sorted(private)} を使っています（ecobuild_cli.kit だけ）"
