"""新しいモジュールの中身（pyproject.toml・パッケージ・テスト）。"""

from __future__ import annotations

from pathlib import Path

NEW_KINDS = ("app", "library", "none")

PYPROJECT = """\
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []
{scripts}
[project.optional-dependencies]
dev = [
    "pytest>=8,<9",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
# 同じ名前のテスト（tests/a/test_x.py と tests/b/test_x.py）を置けるようにする
addopts = ["--import-mode=importlib"]
"""

MAIN = '''\
"""{name} の実行（ecobuild run／{name} コマンド／python -m {package}）。"""


def main() -> None:
    print("Hello from {name}")


if __name__ == "__main__":
    main()
'''

IMPORT_TEST = '''\
import {package}


def test_import():
    assert {package}.__doc__
'''


def package_name(module_name: str, project: str | None) -> str:
    return (project or module_name).lower()


def populate(root: Path, module_name: str, kind: str, project: str | None) -> None:
    package = package_name(module_name, project)
    scripts = f'\n[project.scripts]\n{module_name} = "{package}.__main__:main"\n' if kind == "app" else ""
    write(root / "pyproject.toml", PYPROJECT.format(name=module_name, scripts=scripts))
    (root / "tests").mkdir(exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    if kind == "none":
        # 空のフォルダーはgitに入らないので、置き場所だけ残す（パッケージは file add で足す）
        write(root / "src" / ".gitkeep", "")
        write(root / "tests" / ".gitkeep", "")
        return
    write(root / "src" / package / "__init__.py", f'"""{module_name}。"""\n')
    if kind == "app":
        write(root / "src" / package / "__main__.py", MAIN.format(name=module_name, package=package))
    write(root / "tests" / f"test_{package}.py", IMPORT_TEST.format(package=package))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
