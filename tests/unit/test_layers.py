"""層の境目（memo/設計.md の「層」）。下の層は上の層を import しない。

    ecotask（タスク管理）→ ecowork（作業の流れ）→ ecobuild（本体）→ ecobuild_cpp・ecobuild_generic・ecobuild_python
    （拡張）→ ecobuild_bundle（本体＋拡張）→ ecobuild_cli（CLI）

あわせて、ecobuild 系は作業の流れを ecowork からだけ使う（ecotask を直接使わない）、他のパッケージの
非公開のもの（_ で始まるモジュール・名前）は使わない、を確かめる。

型の拡張の cli パッケージ（ecobuild_<型>.cli）は、その型のコマンド＝CLI の層。ecobuild_cli の公開の補助
（ecobuild_cli.kit）だけを使い、click・CLIFrameWork は使わない。型の本体は cli を import しない。
"""

import ast
import importlib
from pathlib import Path

import pytest

TYPES = ("ecobuild_cpp", "ecobuild_generic", "ecobuild_python")
UPPER_THAN_CORE = {"ecobuild_bundle", "ecobuild_cli"} | set(TYPES)
CLI_LIBRARIES = {"click", "cli_framework"}
ECOBUILD = {"ecobuild"} | UPPER_THAN_CORE

# パッケージ → import してはいけないもの（パッケージの先頭の名前）
FORBIDDEN = {
    "ecotask": {"ecowork", "cppbuild"} | ECOBUILD | CLI_LIBRARIES,
    "ecowork": {"cppbuild"} | ECOBUILD | CLI_LIBRARIES,
    "ecobuild": {"ecotask", "cppbuild"} | UPPER_THAN_CORE | CLI_LIBRARIES,
    "ecobuild_cpp": {"ecotask", "ecobuild_bundle", "ecobuild_cli", "ecobuild_generic", "ecobuild_python"} | CLI_LIBRARIES,
    "ecobuild_generic": {"ecotask", "ecobuild_bundle", "ecobuild_cli", "ecobuild_cpp", "ecobuild_python",
                         "cppbuild"} | CLI_LIBRARIES,
    "ecobuild_python": {"ecotask", "ecobuild_bundle", "ecobuild_cli", "ecobuild_cpp", "ecobuild_generic",
                        "cppbuild"} | CLI_LIBRARIES,
    "ecobuild_bundle": {"ecotask", "ecobuild_cli"} | CLI_LIBRARIES,
    # CLI は型を知らない（型のコマンドは登録した型の cli パッケージを名前で読み込む）
    "ecobuild_cli": {"ecotask", "cppbuild"} | set(TYPES),
}


def _imports(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    """(import したモジュール, そこから取り出した名前) の一覧。相対の import は含めない。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(a.name, ()) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module, tuple(a.name for a in node.names)))
    return found


def _imports_type_commands(path: Path, package: str) -> bool:
    """型の本体が、型のコマンド（cli）を import しているか（相対の import も見る）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and (node.module or "").startswith(f"{package}.cli"):
                return True
            if node.level and ((node.module or "").split(".")[0] == "cli" or any(a.name == "cli" for a in node.names)):
                return True
        elif isinstance(node, ast.Import) and any(a.name.startswith(f"{package}.cli") for a in node.names):
            return True
    return False


def _root(package: str) -> Path:
    return Path(importlib.import_module(package).__file__).parent


def _sources(package: str) -> list[Path]:
    """パッケージの本体のソース（型の拡張は、型のコマンド cli/ を除く。cli/ は CLI の層として下で確かめる）。"""
    root = _root(package)
    sources = sorted(p for p in root.rglob("*.py")
                     if not (package in TYPES and p.relative_to(root).parts[:1] == ("cli",)))
    assert sources
    return sources


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_lower_layers_do_not_import_upper_layers(package):
    root = _root(package)
    for path in _sources(package):
        found = {module.split(".")[0] for module, _ in _imports(path)} & FORBIDDEN[package]
        assert not found, f"{path.relative_to(root.parent)} が {sorted(found)} を import しています"
        if package in TYPES:
            assert not _imports_type_commands(path, package), \
                f"{path.relative_to(root.parent)} が型のコマンド（cli）を import しています"


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_packages_do_not_use_private_parts_of_other_packages(package):
    root = _root(package)
    paths = sorted(root.rglob("*.py"))
    for path in paths:
        for module, names in _imports(path):
            if module.split(".")[0] not in FORBIDDEN or module.split(".")[0] == package:
                continue
            private = [part for part in module.split(".")[1:] if part.startswith("_")]
            private += [name for name in names if name.startswith("_")]
            assert not private, f"{path.relative_to(root.parent)} が {module} の非公開のもの {private} を使っています"


@pytest.mark.parametrize("package", TYPES)
def test_type_commands_use_only_the_public_cli_helpers(package):
    root = _root(package) / "cli"
    others = set(TYPES) - {package}
    for path in root.rglob("*.py"):
        modules = {module for module, _ in _imports(path)}
        found = {name.split(".")[0] for name in modules} & ({"ecotask", "cppbuild"} | CLI_LIBRARIES | others)
        assert not found, f"{path.relative_to(root.parent.parent)} が {sorted(found)} を import しています"
        private = {name for name in modules if name.startswith("ecobuild_cli") and name != "ecobuild_cli.kit"}
        assert not private, f"{path.relative_to(root.parent.parent)} が {sorted(private)} を使っています（ecobuild_cli.kit だけ）"
