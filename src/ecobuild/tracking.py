"""管理するファイル：新しいファイルのうち、task commit が自動でコミットに含めるもの（許可の一覧）。

.gitignore（gitに見せないもの）とは別に、「管理するファイル」に当たる新しいファイルだけを自動で含める。
変な拡張子のファイルが紛れても、うかつにコミットしないため。一度コミットしたファイルは、その後の変更・削除を必ず含める。

決まり方（足し合わせ）：本体が作るファイル（BUILT_IN）＋型の既定（ModuleType.tracked_patterns）＋
ecobuild.toml の [files] include。[files] exclude は型の既定と include から外す（本体と型の管理ファイルは外せない）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

TABLE = "files"

# ECOBuild が作り、常に管理するファイル
BUILT_IN = ("/.ecobuild/ecobuild.toml", "/.ecobuild/.gitignore", "/.ecobuild/.gitattributes", "/.ecobuild/README.md", "/README.md",
            "/AGENTS.md", "/.gitignore",
            "/.gitattributes", "/.github/workflows/*.yml", "/.github/workflows/*.yaml")

BUILT_IN_SOURCE = "ecobuild"
TYPE_SOURCE = "type"
MODULE_SOURCE = "module"


@dataclass(frozen=True)
class TrackedPattern:
    pattern: str
    source: str                      # ecobuild（本体）・type（型の既定）・module（ecobuild.toml の [files] include）
    excluded: bool = False           # [files] exclude で外している（型の既定のうち）


@dataclass(frozen=True)
class TrackedFiles:
    """管理するファイルの一覧（ecobuild track）。"""
    patterns: tuple[TrackedPattern, ...]
    exclude: tuple[str, ...]         # ecobuild.toml の [files] exclude
    managed_note: str = ""           # 型の管理ファイル（生成ファイル等）。パターンとは別に常に含める


def normalize(pattern: str) -> str:
    """書き方をそろえる（区切りは /、前後の空白を除く）。空なら空。"""
    return pattern.strip().replace("\\", "/")


def matches(pattern: str, path: str) -> bool:
    """パターンが、モジュールのルートからの相対パス（/ 区切り）に当たるか（.gitignore と同じ考え方）。

    / を含まないパターンは、どの階層の名前にも当たる。含むものはルートからの相対（先頭の / は省いてよい）。
    * は / 以外の0文字以上、? は / 以外の1文字、** は0個以上の階層。末尾が / なら、そのフォルダーの中のすべて。
    """
    return _regex(normalize(pattern)).fullmatch(path.replace("\\", "/")) is not None


@lru_cache(maxsize=256)
def _regex(pattern: str) -> re.Pattern:
    anchored = "/" in pattern.rstrip("/")
    if pattern.endswith("/"):
        pattern += "**"
    pattern = pattern.lstrip("/")
    parts = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    body = "".join(parts)
    return re.compile(body if anchored else f"(?:.*/)?{body}")


def module_lists(extra: dict) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """ecobuild.toml の [files] の include・exclude。"""
    from .errors import EcoBuildError, ErrorCode
    table = extra.get(TABLE, {})
    result = []
    for key in ("include", "exclude"):
        value = table.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise EcoBuildError(ErrorCode.INVALID_CONFIG,
                                f"[{TABLE}] の {key} は文字列の配列です（例：{key} = [\"*.txt\"]）。")
        result.append(tuple(normalize(item) for item in value if normalize(item)))
    return result[0], result[1]


def with_lists(extra: dict, include: tuple[str, ...], exclude: tuple[str, ...]) -> dict:
    """[files] を include・exclude に置き換えた型ごとの表（どちらも空なら [files] を消す）。"""
    table = {key: list(values) for key, values in (("include", include), ("exclude", exclude)) if values}
    others = {key: value for key, value in extra.items() if key != TABLE}
    return {**others, TABLE: table} if table else others
