"""module rename の型 python の分：パッケージ名を新しいモジュール名に合わせる。

変えるもの（前の名前に合わせてあるものだけ）：
- pyproject.toml の [project] name（前のモジュール名と同じなら）、[project.scripts]・[project.gui-scripts]・
  [project.entry-points.*] の前のモジュール名のコマンド名、前のパッケージ（前の名前の小文字）を指す文字列
  （"calc.__main__:main"・"src/calc" 等）。
- src/<前のパッケージ>/ → src/<新しいパッケージ>/、tests/test_<前のパッケージ>.py → tests/test_<新しいパッケージ>.py。
- .py の import（from calc … ・import calc …）と、そのまま import したファイルでの calc.… の使い方、前のパッケージの
  中を指す文字列（"calc.core.add" 等。mock の場所）。コメント・ほかの文字列（"calc.csv" 等）は変えない（tokenize）。

パッケージ名はモジュール名の小文字（module new と同じ）。違う名前のパッケージ（--project で作った等）は変えない。
"""

from __future__ import annotations

import io
import os
import re
import tokenize
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
        edited = _pyproject(text, previous, name, old, new, root / "src" / old)
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
        edited = _imports(text, old, new, sources / old)
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


def _pyproject(text: str, previous: str, name: str, old: str, new: str, package: Path) -> str:
    """pyproject.toml の名前（行ごとに。書き方・説明はそのまま）。[project] の表では name だけを変え、ほかの表（scripts・
    [tool.*] 等）では、前のパッケージを指す文字列（"calc"・"src/calc"・"calc.__main__:main" 等。_module_path）だけを変える。"""
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
            lines.append(line)
            continue
        if table in _SCRIPT_TABLES or table.startswith("project.entry-points."):
            found = re.match(r"""(\s*)(["']?)([^"'=\s]+)\2(\s*=)""", line)
            if found and found.group(3) == previous:
                line = f"{found.group(1)}{found.group(2)}{name}{found.group(2)}{line[found.start(4):]}"
        if old != new:
            line = re.sub(r"""(["'])([^"'\\]*)\1""", lambda match: _package_string(match, old, new, package), line)
        lines.append(line)
    return "".join(lines)


def _package_string(match: re.Match, old: str, new: str, package: Path) -> str:
    content = match.group(2)
    if content in (old, f"src/{old}") or content.startswith(f"src/{old}/") \
            or _module_path(content, old, package, entry_point=True):
        return match.group(1) + content.replace(old, new, 1) + match.group(1)
    return match.group(0)


def _module_path(content: str, old: str, package: Path, *, entry_point: bool = False) -> bool:
    """content が前のパッケージの中のものを指す名前か（"calc.core"・"calc.core:main"。entry_point なら "calc:main" も）。
    "calc.csv" のようなファイル名と取り違えないよう、次の段が src/<前のパッケージ>/ にあるものだけ。"""
    found = re.fullmatch(rf"{re.escape(old)}((?:\.\w+)*)(:[\w.]+)?", content)
    if found is None:
        return False
    parts = found.group(1).split(".")[1:]
    if not parts:
        return entry_point and found.group(2) is not None
    return (package / parts[0]).is_dir() or (package / f"{parts[0]}.py").is_file()


def _imports(text: str, old: str, new: str, package: Path) -> str:
    """.py の書き換え（tokenize で。コメント・ほかの文字列は変えない）：import の前のパッケージ名、そのまま import したとき
    （import calc）の calc.… の使い方、前のパッケージの中を指す文字列（"calc.core.add" 等。mock の場所）。"""
    lines = io.StringIO(text).readlines()
    try:
        tokens = list(tokenize.generate_tokens(iter(lines).__next__))
    except (tokenize.TokenError, SyntaxError, StopIteration):
        return text
    skipped = (tokenize.COMMENT, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER)
    code = [t for t in tokens if t.type not in skipped]
    starts = []   # その字句を含む文の最初の字句
    statement = None
    for token in code:
        statement = statement or token
        starts.append(statement)
        if token.type == tokenize.NEWLINE or (token.type == tokenize.OP and token.string == ";"):
            statement = None
    imported, plain = [], False
    for index, token in enumerate(code):
        if token.type != tokenize.NAME or token.string != old or not index:
            continue
        before, first = code[index - 1], starts[index]
        after = code[index + 1] if index + 1 < len(code) else None
        if before.type == tokenize.NAME and before.string in ("import", "from") and first.string in ("import", "from"):
            imported.append(index)
            if before.string == "import" and first.string == "import" and not (after and after.string == "as"):
                plain = True
    edits = list(imported)
    if plain:   # import calc の後の calc.…（ほかのものの属性 x.calc は除く）
        edits += [index for index, t in enumerate(code) if t.type == tokenize.NAME and t.string == old
                  and index not in imported and index + 1 < len(code) and code[index + 1].string == "."
                  and not (index and code[index - 1].string == ".")]
    replacements = [(code[index].start, code[index].end, new) for index in edits]
    for token in code:
        quote = token.string[:1]
        if token.type == tokenize.STRING and quote in ("'", '"') and token.string[:3] != quote * 3:
            content = token.string[1:-1]
            if _module_path(content, old, package):
                replacements.append((token.start, token.end, quote + new + content[len(old):] + quote))
    if not replacements:
        return text
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    result = text
    for (row, column), (end_row, end_column), value in sorted(replacements, reverse=True):
        result = result[:offsets[row - 1] + column] + value + result[offsets[end_row - 1] + end_column:]
    return result


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
