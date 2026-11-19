"""module rename の型 python の分：パッケージ名を新しいモジュール名に合わせる。

変えるもの（前の名前に合わせてあるものだけ）：
- pyproject.toml の [project] name（前のモジュール名と同じなら）、[project.scripts]・[project.gui-scripts]・
  [project.entry-points.*] の前のモジュール名のコマンド名、前のパッケージ（前の名前の小文字）を指す文字列
  （"calc.__main__:main"・"src/calc" 等）。
- src/<前のパッケージ>/ → src/<新しいパッケージ>/、tests/test_<前のパッケージ>.py → tests/test_<新しいパッケージ>.py。
- .py の import（from calc … ・import calc …）と、そのまま import したファイルでの calc.… の使い方、"calc.x" の形の文字列
  （mock の場所等）。

パッケージ名はモジュール名の小文字（module new と同じ）。違う名前のパッケージ（--project で作った等）は変えない。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import _python

_SKIPPED_FOLDERS = {".git", ".venv", "venv", "build", "dist", "deps", "node_modules", "__pycache__"}
_SCRIPT_TABLES = ("project.scripts", "project.gui-scripts")


def rename(root: Path, previous: str, name: str, *, dry_run: bool = False) -> tuple[str, ...]:
    """変えた（dry_run なら変える）ファイル（ルートからの場所。移すものは元と先）。"""
    old, new = previous.lower(), name.lower()
    changed: list[str] = []
    pyproject = root / _python.PYPROJECT
    if pyproject.is_file():
        text = pyproject.read_bytes().decode("utf-8")
        edited = _pyproject(text, previous, name, old, new)
        if edited != text:
            changed.append(_python.PYPROJECT)
            if not dry_run:
                _write(pyproject, edited)
    if old == new:
        return tuple(changed)
    sources = root / "src"
    moves = []
    if (sources / old).is_dir() and not (sources / new).exists():
        moves.append((f"src/{old}", f"src/{new}"))
    test = root / "tests" / f"test_{old}.py"
    if test.is_file() and not (root / "tests" / f"test_{new}.py").exists():
        moves.append((f"tests/test_{old}.py", f"tests/test_{new}.py"))
    for origin, target in moves:
        changed += [origin, target]
    for path in _python_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:   # UTF-8 でないファイルは変えない
            continue
        edited = _imports(text, old, new)
        if edited == text:
            continue
        shown = relative
        for origin, target in moves:
            if relative == origin or relative.startswith(origin + "/"):
                shown = target + relative[len(origin):]
        changed.append(shown)
        if not dry_run:
            _write(path, edited)
    if not dry_run:
        for origin, target in moves:
            (root / origin).rename(root / target)
    return tuple(dict.fromkeys(changed))


def _pyproject(text: str, previous: str, name: str, old: str, new: str) -> str:
    """pyproject.toml の名前（行ごとに。書き方・説明はそのまま）。"""
    table = ""
    lines = []
    for line in text.splitlines(keepends=True):
        heading = re.match(r"\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(#.*)?$", line)
        if heading:
            table = heading.group(1).replace('"', "").replace("'", "").replace(" ", "")
            lines.append(line)
            continue
        if table == "project":
            found = re.match(r"""(\s*name\s*=\s*)(["'])(.*?)\2""", line)
            if found and _normalized(found.group(3)) == _normalized(previous):
                line = f"{found.group(1)}{found.group(2)}{name}{found.group(2)}{line[found.end():]}"
        if table in _SCRIPT_TABLES or table.startswith("project.entry-points."):
            found = re.match(r"""(\s*)(["']?)([^"'=\s]+)\2(\s*=)""", line)
            if found and found.group(3) == previous:
                line = f"{found.group(1)}{found.group(2)}{name}{found.group(2)}{line[found.start(4):]}"
        if old != new:
            line = re.sub(rf"""(["'])((?:src/)?){re.escape(old)}(?=["'./:])""", rf"\g<1>\g<2>{new}", line)
        lines.append(line)
    return "".join(lines)


def _imports(text: str, old: str, new: str) -> str:
    """.py の import と、そのまま import した名前の使い方、"<パッケージ>.x" の形の文字列。"""
    plain = re.search(rf"(?m)^\s*import\s+{re.escape(old)}(?:\.\w+)*\s*(?:#.*)?$", text) is not None
    text = re.sub(rf"(?m)^(\s*(?:from|import)\s+){re.escape(old)}(?=[\s.,]|$)", rf"\g<1>{new}", text)
    if plain:
        text = re.sub(rf"""(?<![\w.'"]){re.escape(old)}(?![\w'"])""", new, text)
    return re.sub(rf"""(["']){re.escape(old)}(?=[.:])""", rf"\g<1>{new}", text)


def _python_files(root: Path) -> list[Path]:
    found = []
    for folder, children, files in os.walk(root):
        children[:] = [c for c in children if c not in _SKIPPED_FOLDERS and not c.startswith(".")]
        found += [Path(folder) / f for f in files if f.endswith(".py")]
    return sorted(found)


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _write(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))
