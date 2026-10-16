"""層の境目（memo/設計.md の「層」）。下の層は上の層を import しない。

    ecotask（タスク管理）→ ecowork（作業の流れ）→ ecobuild（本体）→ ecobuild_cpp・ecobuild_generic（拡張）
    → ecobuild_bundle（本体＋拡張）→ ecobuild_cli（CLI）

あわせて、ecobuild 系は作業の流れを ecowork からだけ使う（ecotask を直接使わない）、他のパッケージの
非公開のもの（_ で始まるモジュール・名前）は使わない、を確かめる。
"""

import ast
import importlib
from pathlib import Path

import pytest

UPPER_THAN_CORE = {"ecobuild_bundle", "ecobuild_cli", "ecobuild_cpp", "ecobuild_generic"}
CLI_LIBRARIES = {"click", "cli_framework"}
ECOBUILD = {"ecobuild"} | UPPER_THAN_CORE

# パッケージ → import してはいけないもの（パッケージの先頭の名前）
FORBIDDEN = {
    "ecotask": {"ecowork", "cppbuild"} | ECOBUILD | CLI_LIBRARIES,
    "ecowork": {"cppbuild"} | ECOBUILD | CLI_LIBRARIES,
    "ecobuild": {"ecotask", "cppbuild"} | UPPER_THAN_CORE | CLI_LIBRARIES,
    "ecobuild_cpp": {"ecotask", "ecobuild_bundle", "ecobuild_cli", "ecobuild_generic"} | CLI_LIBRARIES,
    "ecobuild_generic": {"ecotask", "ecobuild_bundle", "ecobuild_cli", "ecobuild_cpp", "cppbuild"} | CLI_LIBRARIES,
    "ecobuild_bundle": {"ecotask", "ecobuild_cli"} | CLI_LIBRARIES,
    "ecobuild_cli": {"ecotask"},
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


def _sources(package: str) -> list[Path]:
    root = Path(importlib.import_module(package).__file__).parent
    sources = sorted(root.rglob("*.py"))
    assert sources
    return sources


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_lower_layers_do_not_import_upper_layers(package):
    for path in _sources(package):
        found = {module.split(".")[0] for module, _ in _imports(path)} & FORBIDDEN[package]
        assert not found, f"{package}/{path.name} が {sorted(found)} を import しています"


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_packages_do_not_use_private_parts_of_other_packages(package):
    for path in _sources(package):
        for module, names in _imports(path):
            if module.split(".")[0] not in FORBIDDEN or module.split(".")[0] == package:
                continue
            private = [part for part in module.split(".")[1:] if part.startswith("_")]
            private += [name for name in names if name.startswith("_")]
            assert not private, f"{package}/{path.name} が {module} の非公開のもの {private} を使っています"
