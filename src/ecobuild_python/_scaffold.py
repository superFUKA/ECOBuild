"""新しいモジュールの中身（pyproject.toml・パッケージ・テスト・.gitattributes）。"""

from __future__ import annotations

from pathlib import Path

NEW_KINDS = ("app", "library", "none")

# ビルドは hatchling：setuptools のように egg-info・build/ をモジュールの中に作らない（コンテナの 9p のマウントの上では
# egg-info の chmod で失敗する）。src/ の中のパッケージはすべて入れる（__init__.py のないフォルダーも）
PYPROJECT = """\
[build-system]
requires = ["hatchling>=1.24"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []
{scripts}
[project.optional-dependencies]
dev = [
    "pytest>=8,<9",
    "pytest-xdist>=3,<4",   # テストを並べて流す（ecobuild test・CI）
]

[tool.hatch.build.targets.wheel]
# src/ の中をすべて入れる（src/ は外す。src/calc/ → calc/）
only-include = ["src"]
sources = ["src"]
exclude = [".gitkeep"]

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


# 改行はLFにそろえる（Windows の core.autocrlf=true で CRLF にされると、コンテナ〔Linux〕のシェル・Python が困る）。
# 新しいモジュールにだけ置く（module upgrade・adopt は足さない：元のリポジトリの .gitattributes の後ろに * の行を
# 足すと、前に書いた *.ps1 等の決まりを上書きしてしまう）
GITATTRIBUTES = """\
* text=auto eol=lf
*.ps1 text eol=crlf
*.cmd text eol=crlf
*.bat text eol=crlf
"""


def package_name(module_name: str, project: str | None) -> str:
    return (project or module_name).lower()


def populate(root: Path, module_name: str, kind: str, project: str | None, *, test: bool = True) -> None:
    """test：パッケージのテスト（tests/test_<パッケージ>.py）も作る（偽なら tests/ は空で置く）。"""
    package = package_name(module_name, project)
    scripts = f'\n[project.scripts]\n{module_name} = "{package}.__main__:main"\n' if kind == "app" else ""
    write(root / "pyproject.toml", PYPROJECT.format(name=module_name, scripts=scripts))
    write(root / ".gitattributes", GITATTRIBUTES)
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
    if test:
        write(root / "tests" / f"test_{package}.py", IMPORT_TEST.format(package=package))
    else:
        write(root / "tests" / ".gitkeep", "")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
